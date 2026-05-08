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

    if not normalized:
        return True

    if normalized in {"BECA", "CORPORATIVO"}:
        return True

    if "PRUEBA" in normalized:
        return True

    return False

def _month_start_for_date(value: date) -> date:
    return date(value.year, value.month, 1)


def _month_end_for_date(value: date) -> date:
    if value.month == 12:
        return date(value.year, 12, 31)

    next_month = date(value.year, value.month + 1, 1)
    return date.fromordinal(next_month.toordinal() - 1)


def _parse_venta_total_row_date(value: Any, *, row_index: int | None = None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    text = str(value or "").strip()

    for date_format in ("%Y-%m-%d", "%d-%m-%y", "%d/%m/%y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    raise TrackSourceDomiciliadosEfectivosDailyServiceError(
        "No se pudo parsear fecha de venta_total "
        f"row_index={row_index}: {value!r}"
    )


def _resolve_venta_total_snapshot_for_track_date(
    *,
    business_date: date,
) -> VentaTotalSnapshotORM:
    exact_snapshot = (
        VentaTotalSnapshotORM.query.filter_by(
            business_date=business_date,
            snapshot_kind="daily",
            is_canonical=True,
        )
        .order_by(VentaTotalSnapshotORM.id.desc())
        .first()
    )

    if exact_snapshot is not None:
        return exact_snapshot

    month_start = _month_start_for_date(business_date)
    month_end = _month_end_for_date(business_date)

    monthly_snapshot = (
        VentaTotalSnapshotORM.query.filter(
            VentaTotalSnapshotORM.business_date >= month_start,
            VentaTotalSnapshotORM.business_date <= month_end,
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
        )
        .order_by(
            VentaTotalSnapshotORM.business_date.desc(),
            VentaTotalSnapshotORM.id.desc(),
        )
        .first()
    )

    if monthly_snapshot is not None:
        return monthly_snapshot

    raise TrackSourceDomiciliadosEfectivosDailyServiceError(
        "No existe snapshot canónico daily de venta_total "
        f"para el mes de business_date={business_date.isoformat()}."
    )

def build_track_source_domiciliados_efectivos_daily_for_date(
    *,
    business_date: Any,
) -> list[dict[str, Any]]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    snapshot = _resolve_venta_total_snapshot_for_track_date(
        business_date=normalized_business_date,
    )

    rows = (
        VentaTotalSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(VentaTotalSnapshotRowORM.row_index.asc())
        .all()
    )

    counts_by_branch: dict[str, int] = {}

    for row in rows:
        row_date = _parse_venta_total_row_date(
            row.fecha,
            row_index=row.row_index,
        )

        if (
            row_date.year != normalized_business_date.year
            or row_date.month != normalized_business_date.month
        ):
            continue

        if row_date > normalized_business_date:
            continue

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
                "business_date": normalized_business_date.isoformat(),
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