#   backend\app\warehouse\services\track_source_domiciliados_efectivos_daily_service.py


from __future__ import annotations

from datetime import date, datetime
from typing import Any
from app.extensions import db


from app.models.warehouse import (
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
    TrackSourceDomiciliadosEfectivosDailyORM,
)
from app.warehouse.services.track_branch_alias_resolver_service import (
    resolve_track_branch_alias,
)


class TrackSourceDomiciliadosEfectivosDailyServiceError(RuntimeError):
    """Error base del builder read-only de domiciliados efectivos."""


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise TrackSourceDomiciliadosEfectivosDailyServiceError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise TrackSourceDomiciliadosEfectivosDailyServiceError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _is_active_status(value: Any) -> bool:
    return str(value or "").strip().upper() == "ACTIVO"


def _is_domiciliado_payment(value: Any) -> bool:
    return "DOMICILIADO" in str(value or "").strip().upper()


def _is_out_of_scope_track_branch(raw_branch_name: str) -> bool:
    normalized = str(raw_branch_name or "").strip().upper()
    return normalized in {"BECA", "CORPORATIVO"}


def build_track_source_domiciliados_efectivos_daily_for_date(
    *,
    business_date: Any,
) -> list[dict[str, Any]]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    snapshot = (
        VentaTotalSnapshotORM.query.filter_by(
            business_date=normalized_business_date,
            snapshot_kind="daily",
            is_canonical=True,
        )
        .order_by(VentaTotalSnapshotORM.id.desc())
        .first()
    )

    if snapshot is None:
        raise TrackSourceDomiciliadosEfectivosDailyServiceError(
            "No existe snapshot canónico daily de venta_total "
            f"para business_date={normalized_business_date.isoformat()}."
        )

    rows = (
        VentaTotalSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(VentaTotalSnapshotRowORM.row_index.asc())
        .all()
    )

    counts_by_branch: dict[str, int] = {}

    for row in rows:
        if _is_out_of_scope_track_branch(row.sucursal):
            continue

        if not _is_active_status(row.estatus):
            continue

        if not _is_domiciliado_payment(row.forma_pago):
            continue

        sucursal_canon = resolve_track_branch_alias(
            source_family="gasca_family",
            raw_branch_name=row.sucursal,
        )

        if sucursal_canon is None:
            raise TrackSourceDomiciliadosEfectivosDailyServiceError(
                "No se pudo resolver alias de sucursal para venta_total: "
                f"{row.sucursal!r}"
            )

        counts_by_branch[sucursal_canon] = counts_by_branch.get(sucursal_canon, 0) + 1

    result: list[dict[str, Any]] = []

    for sucursal_canon, count in sorted(counts_by_branch.items()):
        result.append(
            {
                "business_date": snapshot.business_date.isoformat(),
                "sucursal_canon": sucursal_canon,
                "nuevos_domiciliados_real_mtd": count,
                "source_snapshot_id": snapshot.id,
                "source_report_type_key": snapshot.report_type_key,
            }
        )

    return result

def refresh_track_source_domiciliados_efectivos_daily_for_date(
    *,
    business_date: Any,
) -> dict[str, Any]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    rows = build_track_source_domiciliados_efectivos_daily_for_date(
        business_date=normalized_business_date,
    )

    try:
        TrackSourceDomiciliadosEfectivosDailyORM.query.filter_by(
            business_date=normalized_business_date
        ).delete(synchronize_session=False)

        for row in rows:
            db.session.add(
                TrackSourceDomiciliadosEfectivosDailyORM(
                    business_date=_ensure_date(
                        row["business_date"],
                        field_name="business_date",
                    ),
                    sucursal_canon=row["sucursal_canon"],
                    nuevos_domiciliados_real_mtd=row["nuevos_domiciliados_real_mtd"],
                    source_snapshot_id=row["source_snapshot_id"],
                    source_report_type_key=row["source_report_type_key"],
                )
            )

        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "refreshed",
        "business_date": normalized_business_date.isoformat(),
        "rows_inserted": len(rows),
    }