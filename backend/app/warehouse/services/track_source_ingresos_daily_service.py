#   backend\app\warehouse\services\track_source_ingresos_daily_service.py


from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.warehouse import (
    IngresosTotalpassSnapshotORM,
    IngresosTotalpassSnapshotRowORM,
    IngresosWellhubSnapshotORM,
    IngresosWellhubSnapshotRowORM,
    ReporteDireccionSnapshotORM,
    ReporteDireccionSnapshotRowORM,
    TrackSourceIngresosDailyORM,
    TrackSourceAgregadorasDailyORM
)
from app.warehouse.services.track_branch_alias_resolver_service import (
    resolve_track_branch_alias,
)



class TrackSourceIngresosDailyServiceError(RuntimeError):
    """Error base del builder read-only de F4."""


_DECIMAL_ZERO = Decimal("0.00")


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


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return _DECIMAL_ZERO

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except Exception as exc:
        raise TrackSourceIngresosDailyServiceError(
            f"No se pudo convertir a Decimal el valor {value!r}"
        ) from exc


def _is_out_of_scope_track_branch(raw_branch_name: str) -> bool:
    normalized = str(raw_branch_name or "").strip().upper()
    return normalized in {"BECA", "CORPORATIVO"}


def _resolve_reporte_direccion_snapshot_for_track(
    *,
    business_date: date,
    generation_mode: str | None = None,
) -> ReporteDireccionSnapshotORM | None:
    query = ReporteDireccionSnapshotORM.query.filter_by(
        business_date=business_date,
        snapshot_kind="daily",
    )

    if generation_mode == "manual_preview":
        return query.order_by(ReporteDireccionSnapshotORM.id.desc()).first()

    return (
        query
        .filter(ReporteDireccionSnapshotORM.is_canonical.is_(True))
        .order_by(ReporteDireccionSnapshotORM.id.desc())
        .first()
    )


def _build_base_ingresos_map_for_date(
    *,
    business_date: date,
    generation_mode: str | None = None,
) -> tuple[dict[str, dict[str, Any]], int]:
    snapshot = _resolve_reporte_direccion_snapshot_for_track(
        business_date=business_date,
        generation_mode=generation_mode,
    )

    if snapshot is None:
        if generation_mode == "manual_preview":
            raise TrackSourceIngresosDailyServiceError(
                f"No existe snapshot daily de reporte_direccion para business_date={business_date.isoformat()}."
            )

        raise TrackSourceIngresosDailyServiceError(
            f"No existe snapshot canónico daily de reporte_direccion para business_date={business_date.isoformat()}."
        )

    rows = (
        ReporteDireccionSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(ReporteDireccionSnapshotRowORM.id.asc())
        .all()
    )

    result: dict[str, dict[str, Any]] = {}

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

        current = result.get(
            sucursal_canon,
            {
                "ingreso_real_base_mtd": _DECIMAL_ZERO,
                "source_snapshot_id_reporte_direccion": snapshot.id,
                "source_report_type_key_reporte_direccion": snapshot.report_type_key,
            },
        )

        current["ingreso_real_base_mtd"] = _to_decimal(
            current["ingreso_real_base_mtd"]
        ) + _to_decimal(row.ingreso_acumulado_mes_en_curso)

        result[sucursal_canon] = current

    return result, snapshot.id
def _build_agregadoras_map_for_date(
    *,
    business_date: date,
) -> dict[str, dict[str, Any]]:
    rows = (
        TrackSourceAgregadorasDailyORM.query.filter_by(
            business_date=business_date,
        )
        .order_by(TrackSourceAgregadorasDailyORM.id.asc())
        .all()
    )

    result: dict[str, dict[str, Any]] = {}

    for row in rows:
        result[row.sucursal_canon] = {
            "ingreso_wellhub_mtd": _to_decimal(row.ingreso_wellhub_mtd),
            "ingreso_totalpass_mtd": _to_decimal(row.ingreso_totalpass_mtd),
            "ingreso_real_agregadora_mtd": _to_decimal(
                row.ingreso_agregadora_total_mtd
            ),
            "source_business_date_agregadoras": row.business_date,
            "source_snapshot_id_wellhub": row.source_snapshot_id_wellhub,
            "source_snapshot_id_totalpass": row.source_snapshot_id_totalpass,
            "source_report_type_key_wellhub": row.source_report_type_key_wellhub,
            "source_report_type_key_totalpass": row.source_report_type_key_totalpass,
        }

    return result

def _resolve_agregadoras_business_date(
    *,
    business_date: date,
    generation_mode: str | None = None,
) -> date:
    if generation_mode != "manual_preview":
        return business_date

    latest_available_row = (
        db.session.query(TrackSourceAgregadorasDailyORM.business_date)
        .filter(TrackSourceAgregadorasDailyORM.business_date <= business_date)
        .order_by(TrackSourceAgregadorasDailyORM.business_date.desc())
        .first()
    )

    if latest_available_row is None or latest_available_row[0] is None:
        return business_date

    return latest_available_row[0]

def _merge_base_and_agregadoras_maps_for_date(
    *,
    business_date: date,
    base_map: dict[str, dict[str, Any]],
    agregadoras_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    all_branch_keys = set(base_map.keys()) | set(agregadoras_map.keys())

    result: list[dict[str, Any]] = []

    for sucursal_canon in sorted(all_branch_keys):
        base_data = base_map.get(sucursal_canon, {})
        agregadoras_data = agregadoras_map.get(sucursal_canon, {})

        ingreso_real_base_mtd = _to_decimal(base_data.get("ingreso_real_base_mtd"))
        ingreso_wellhub_mtd = _to_decimal(agregadoras_data.get("ingreso_wellhub_mtd"))
        ingreso_totalpass_mtd = _to_decimal(
            agregadoras_data.get("ingreso_totalpass_mtd")
        )
        ingreso_real_agregadora_mtd = _to_decimal(
            agregadoras_data.get("ingreso_real_agregadora_mtd")
        )
        ingreso_real_total_mtd = ingreso_real_base_mtd + ingreso_real_agregadora_mtd

        result.append(
            {
                "business_date": business_date.isoformat(),
                "sucursal_canon": sucursal_canon,
                "ingreso_real_base_mtd": ingreso_real_base_mtd,
                "ingreso_wellhub_mtd": ingreso_wellhub_mtd,
                "ingreso_totalpass_mtd": ingreso_totalpass_mtd,
                "ingreso_real_agregadora_mtd": ingreso_real_agregadora_mtd,
                "ingreso_real_total_mtd": ingreso_real_total_mtd,
                "ingreso_real_mtd": ingreso_real_total_mtd,

                # compatibilidad legacy
                "source_snapshot_id": base_data.get(
                    "source_snapshot_id_reporte_direccion"
                ),
                "source_report_type_key": base_data.get(
                    "source_report_type_key_reporte_direccion"
                ),

                "source_snapshot_id_reporte_direccion": base_data.get(
                    "source_snapshot_id_reporte_direccion"
                ),
                "source_snapshot_id_wellhub": agregadoras_data.get(
                    "source_snapshot_id_wellhub"
                ),
                "source_snapshot_id_totalpass": agregadoras_data.get(
                    "source_snapshot_id_totalpass"
                ),
                "source_business_date_agregadoras": agregadoras_data.get(
                    "source_business_date_agregadoras"
                ),
                "source_report_type_key_reporte_direccion": base_data.get(
                    "source_report_type_key_reporte_direccion"
                ),
                "source_report_type_key_wellhub": agregadoras_data.get(
                    "source_report_type_key_wellhub"
                ),
                "source_report_type_key_totalpass": agregadoras_data.get(
                    "source_report_type_key_totalpass"
                ),
            }
        )

    return result

def _build_wellhub_ingresos_map_for_date(
    *,
    business_date: date,
) -> tuple[dict[str, dict[str, Any]], int | None]:
    snapshot = (
        IngresosWellhubSnapshotORM.query.filter_by(
            business_date=business_date,
            snapshot_kind="daily",
            is_canonical=True,
        )
        .order_by(IngresosWellhubSnapshotORM.id.desc())
        .first()
    )

    if snapshot is None:
        return {}, None

    rows = (
        IngresosWellhubSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(IngresosWellhubSnapshotRowORM.id.asc())
        .all()
    )

    result: dict[str, dict[str, Any]] = {}

    for row in rows:
        current = result.get(
            row.sucursal_canon,
            {
                "ingreso_wellhub_mtd": _DECIMAL_ZERO,
                "source_snapshot_id_wellhub": snapshot.id,
                "source_report_type_key_wellhub": snapshot.report_type_key,
            },
        )

        current["ingreso_wellhub_mtd"] = _to_decimal(
            current["ingreso_wellhub_mtd"]
        ) + _to_decimal(row.pago_total_mtd)

        result[row.sucursal_canon] = current

    return result, snapshot.id


def _build_totalpass_ingresos_map_for_date(
    *,
    business_date: date,
) -> tuple[dict[str, dict[str, Any]], int | None]:
    snapshot = (
        IngresosTotalpassSnapshotORM.query.filter_by(
            business_date=business_date,
            snapshot_kind="daily",
            is_canonical=True,
        )
        .order_by(IngresosTotalpassSnapshotORM.id.desc())
        .first()
    )

    if snapshot is None:
        return {}, None

    rows = (
        IngresosTotalpassSnapshotRowORM.query.filter_by(snapshot_id=snapshot.id)
        .order_by(IngresosTotalpassSnapshotRowORM.id.asc())
        .all()
    )

    result: dict[str, dict[str, Any]] = {}

    for row in rows:
        result[row.sucursal_canon] = {
            "ingreso_totalpass_mtd": _to_decimal(row.monto_acumulado_mes),
            "source_snapshot_id_totalpass": snapshot.id,
            "source_report_type_key_totalpass": snapshot.report_type_key,
        }

    return result, snapshot.id


def _merge_ingresos_maps_for_date(
    *,
    business_date: date,
    base_map: dict[str, dict[str, Any]],
    wellhub_map: dict[str, dict[str, Any]],
    totalpass_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    all_branch_keys = set(base_map.keys()) | set(wellhub_map.keys()) | set(
        totalpass_map.keys()
    )

    result: list[dict[str, Any]] = []

    for sucursal_canon in sorted(all_branch_keys):
        base_data = base_map.get(sucursal_canon, {})
        wellhub_data = wellhub_map.get(sucursal_canon, {})
        totalpass_data = totalpass_map.get(sucursal_canon, {})

        ingreso_real_base_mtd = _to_decimal(base_data.get("ingreso_real_base_mtd"))
        ingreso_wellhub_mtd = _to_decimal(wellhub_data.get("ingreso_wellhub_mtd"))
        ingreso_totalpass_mtd = _to_decimal(totalpass_data.get("ingreso_totalpass_mtd"))
        ingreso_real_agregadora_mtd = ingreso_wellhub_mtd + ingreso_totalpass_mtd
        ingreso_real_total_mtd = ingreso_real_base_mtd + ingreso_real_agregadora_mtd

        result.append(
            {
                "business_date": business_date.isoformat(),
                "sucursal_canon": sucursal_canon,
                "ingreso_real_base_mtd": ingreso_real_base_mtd,
                "ingreso_wellhub_mtd": ingreso_wellhub_mtd,
                "ingreso_totalpass_mtd": ingreso_totalpass_mtd,
                "ingreso_real_agregadora_mtd": ingreso_real_agregadora_mtd,
                "ingreso_real_total_mtd": ingreso_real_total_mtd,
                "ingreso_real_mtd": ingreso_real_total_mtd,

                # compatibilidad legacy
                "source_snapshot_id": base_data.get(
                    "source_snapshot_id_reporte_direccion"
                ),
                "source_report_type_key": base_data.get(
                    "source_report_type_key_reporte_direccion"
                ),

                "source_snapshot_id_reporte_direccion": base_data.get(
                    "source_snapshot_id_reporte_direccion"
                ),
                "source_snapshot_id_wellhub": wellhub_data.get(
                    "source_snapshot_id_wellhub"
                ),
                "source_snapshot_id_totalpass": totalpass_data.get(
                    "source_snapshot_id_totalpass"
                ),
                "source_report_type_key_reporte_direccion": base_data.get(
                    "source_report_type_key_reporte_direccion"
                ),
                "source_report_type_key_wellhub": wellhub_data.get(
                    "source_report_type_key_wellhub"
                ),
                "source_report_type_key_totalpass": totalpass_data.get(
                    "source_report_type_key_totalpass"
                ),
            }
        )

    return result

def build_track_source_ingresos_daily_for_date(
    *,
    business_date: Any,
    generation_mode: str | None = None,
) -> list[dict[str, Any]]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    base_map, _base_snapshot_id = _build_base_ingresos_map_for_date(
        business_date=normalized_business_date,
        generation_mode=generation_mode,
    )
    agregadoras_business_date = _resolve_agregadoras_business_date(
        business_date=normalized_business_date,
        generation_mode=generation_mode,
    )

    agregadoras_map = _build_agregadoras_map_for_date(
        business_date=agregadoras_business_date,
    )

    return _merge_base_and_agregadoras_maps_for_date(
        business_date=normalized_business_date,
        base_map=base_map,
        agregadoras_map=agregadoras_map,
    )

def refresh_track_source_ingresos_daily_for_date(
    *,
    business_date: Any,
    generation_mode: str | None = None,
) -> dict[str, Any]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    rows = build_track_source_ingresos_daily_for_date(
        business_date=normalized_business_date,
        generation_mode=generation_mode,
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
                    ingreso_real_base_mtd=row["ingreso_real_base_mtd"],
                    ingreso_wellhub_mtd=row["ingreso_wellhub_mtd"],
                    ingreso_totalpass_mtd=row["ingreso_totalpass_mtd"],
                    ingreso_real_agregadora_mtd=row["ingreso_real_agregadora_mtd"],
                    ingreso_real_total_mtd=row["ingreso_real_total_mtd"],
                    ingreso_real_mtd=row["ingreso_real_mtd"],
                    source_snapshot_id=row["source_snapshot_id"],
                    source_report_type_key=row["source_report_type_key"],
                    source_snapshot_id_reporte_direccion=row[
                        "source_snapshot_id_reporte_direccion"
                    ],
                    source_snapshot_id_wellhub=row["source_snapshot_id_wellhub"],
                    source_snapshot_id_totalpass=row["source_snapshot_id_totalpass"],
                    source_business_date_agregadoras=row.get(
                        "source_business_date_agregadoras"
                    ),
                    source_report_type_key_reporte_direccion=row[
                        "source_report_type_key_reporte_direccion"
                    ],
                    source_report_type_key_wellhub=row[
                        "source_report_type_key_wellhub"
                    ],
                    source_report_type_key_totalpass=row[
                        "source_report_type_key_totalpass"
                    ],
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