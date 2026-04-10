#   backend\app\warehouse\services\track_source_ingresos_daily_service.py


from __future__ import annotations

from datetime import date, datetime
from typing import Any
from app.extensions import db

from app.models.warehouse import (
    ReporteDireccionSnapshotORM,
    ReporteDireccionSnapshotRowORM,
    TrackSourceIngresosDailyORM,
)
from app.warehouse.services.track_branch_alias_resolver_service import (
    resolve_track_branch_alias,
)


class TrackSourceIngresosDailyServiceError(RuntimeError):
    """Error base del builder read-only de F4."""


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise TrackSourceIngresosDailyServiceError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise TrackSourceIngresosDailyServiceError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _is_out_of_scope_track_branch(raw_branch_name: str) -> bool:
    normalized = str(raw_branch_name or "").strip().upper()
    return normalized in {"BECA", "CORPORATIVO"}


def build_track_source_ingresos_daily_for_date(
    *,
    business_date: Any,
) -> list[dict[str, Any]]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    snapshot = (
        ReporteDireccionSnapshotORM.query.filter_by(
            business_date=normalized_business_date,
            snapshot_kind="daily",
            is_canonical=True,
        )
        .order_by(ReporteDireccionSnapshotORM.id.desc())
        .first()
    )

    if snapshot is None:
        raise TrackSourceIngresosDailyServiceError(
            f"No existe snapshot canónico daily de reporte_direccion para business_date={normalized_business_date.isoformat()}."
        )

    rows = (
        ReporteDireccionSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(ReporteDireccionSnapshotRowORM.id.asc())
        .all()
    )

    result: list[dict[str, Any]] = []

    for row in rows:
        if _is_out_of_scope_track_branch(row.sucursal):
            continue

        sucursal_canon = resolve_track_branch_alias(
            source_family="gasca_family",
            raw_branch_name=row.sucursal,
        )

        if sucursal_canon is None:
            raise TrackSourceIngresosDailyServiceError(
                f"No se pudo resolver alias de sucursal para reporte_direccion: {row.sucursal!r}"
            )

        result.append(
            {
                "business_date": snapshot.business_date.isoformat(),
                "sucursal_canon": sucursal_canon,
                "ingreso_real_mtd": row.ingreso_acumulado_mes_en_curso,
                "source_snapshot_id": snapshot.id,
                "source_report_type_key": snapshot.report_type_key,
            }
        )

    return result

def refresh_track_source_ingresos_daily_for_date(
    *,
    business_date: Any,
) -> dict[str, Any]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    rows = build_track_source_ingresos_daily_for_date(
        business_date=normalized_business_date,
    )

    try:
        TrackSourceIngresosDailyORM.query.filter_by(
            business_date=normalized_business_date
        ).delete(synchronize_session=False)

        for row in rows:
            db.session.add(
                TrackSourceIngresosDailyORM(
                    business_date=_ensure_date(
                        row["business_date"],
                        field_name="business_date",
                    ),
                    sucursal_canon=row["sucursal_canon"],
                    ingreso_real_mtd=row["ingreso_real_mtd"],
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