# backend/app/warehouse/services/track_source_agregadoras_daily_service.py

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.warehouse import (
    IngresosTotalpassSnapshotORM,
    IngresosTotalpassSnapshotRowORM,
    IngresosWellhubSnapshotORM,
    IngresosWellhubSnapshotRowORM,
    TrackSourceAgregadorasDailyORM,
)


class TrackSourceAgregadorasDailyServiceError(RuntimeError):
    """Error base del builder de la fuente puente de agregadoras."""


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
            raise TrackSourceAgregadorasDailyServiceError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise TrackSourceAgregadorasDailyServiceError(
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
        raise TrackSourceAgregadorasDailyServiceError(
            f"No se pudo convertir a Decimal el valor {value!r}"
        ) from exc


def _build_wellhub_map_for_date(
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


def _build_totalpass_map_for_date(
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
        current = result.get(
            row.sucursal_canon,
            {
                "ingreso_totalpass_mtd": _DECIMAL_ZERO,
                "source_snapshot_id_totalpass": snapshot.id,
                "source_report_type_key_totalpass": snapshot.report_type_key,
            },
        )

        current["ingreso_totalpass_mtd"] = _to_decimal(
            current["ingreso_totalpass_mtd"]
        ) + _to_decimal(row.monto_acumulado_mes)

        result[row.sucursal_canon] = current

    return result, snapshot.id


def _merge_agregadoras_maps_for_date(
    *,
    business_date: date,
    wellhub_map: dict[str, dict[str, Any]],
    totalpass_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    all_branch_keys = set(wellhub_map.keys()) | set(totalpass_map.keys())

    result: list[dict[str, Any]] = []

    for sucursal_canon in sorted(all_branch_keys):
        wellhub_data = wellhub_map.get(sucursal_canon, {})
        totalpass_data = totalpass_map.get(sucursal_canon, {})

        ingreso_wellhub_mtd = _to_decimal(
            wellhub_data.get("ingreso_wellhub_mtd")
        )
        ingreso_totalpass_mtd = _to_decimal(
            totalpass_data.get("ingreso_totalpass_mtd")
        )
        ingreso_agregadora_total_mtd = ingreso_wellhub_mtd + ingreso_totalpass_mtd

        result.append(
            {
                "business_date": business_date.isoformat(),
                "sucursal_canon": sucursal_canon,
                "ingreso_wellhub_mtd": ingreso_wellhub_mtd,
                "ingreso_totalpass_mtd": ingreso_totalpass_mtd,
                "ingreso_agregadora_total_mtd": ingreso_agregadora_total_mtd,
                "source_snapshot_id_wellhub": wellhub_data.get(
                    "source_snapshot_id_wellhub"
                ),
                "source_snapshot_id_totalpass": totalpass_data.get(
                    "source_snapshot_id_totalpass"
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


def build_track_source_agregadoras_daily_for_date(
    *,
    business_date: Any,
) -> list[dict[str, Any]]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    wellhub_map, _wellhub_snapshot_id = _build_wellhub_map_for_date(
        business_date=normalized_business_date,
    )
    totalpass_map, _totalpass_snapshot_id = _build_totalpass_map_for_date(
        business_date=normalized_business_date,
    )

    return _merge_agregadoras_maps_for_date(
        business_date=normalized_business_date,
        wellhub_map=wellhub_map,
        totalpass_map=totalpass_map,
    )


def refresh_track_source_agregadoras_daily_for_date(
    *,
    business_date: Any,
) -> dict[str, Any]:
    normalized_business_date = _ensure_date(
        business_date,
        field_name="business_date",
    )

    rows = build_track_source_agregadoras_daily_for_date(
        business_date=normalized_business_date,
    )

    try:
        TrackSourceAgregadorasDailyORM.query.filter_by(
            business_date=normalized_business_date
        ).delete(synchronize_session=False)

        for row in rows:
            db.session.add(
                TrackSourceAgregadorasDailyORM(
                    business_date=_ensure_date(
                        row["business_date"],
                        field_name="business_date",
                    ),
                    sucursal_canon=row["sucursal_canon"],
                    ingreso_wellhub_mtd=row["ingreso_wellhub_mtd"],
                    ingreso_totalpass_mtd=row["ingreso_totalpass_mtd"],
                    ingreso_agregadora_total_mtd=row["ingreso_agregadora_total_mtd"],
                    source_snapshot_id_wellhub=row["source_snapshot_id_wellhub"],
                    source_snapshot_id_totalpass=row["source_snapshot_id_totalpass"],
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