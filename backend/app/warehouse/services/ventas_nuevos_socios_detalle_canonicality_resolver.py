from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


REPORT_TYPE_KEY = "ventas_nuevos_socios_detalle"
SNAPSHOT_KIND = "month_to_date"


def _aware_utc(
    value: datetime,
    *,
    field_name: str,
) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(
            f"{field_name} debe ser datetime."
        )

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name} debe incluir timezone."
        )

    return value.astimezone(timezone.utc)


def _existing_datetime(
    snapshot: Any,
) -> datetime:
    value = getattr(snapshot, "captured_at", None)

    if not isinstance(value, datetime):
        return datetime.min.replace(
            tzinfo=timezone.utc
        )

    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def resolve_ventas_nuevos_socios_detalle_canonicality(
    *,
    report_type_key: str,
    business_date: date,
    date_from: date,
    date_to: date,
    snapshot_kind: str,
    existing_canonical_snapshot: Any | None,
    captured_at: datetime,
    row_count_valid: int,
    row_count_rejected: int,
) -> dict[str, Any]:
    if report_type_key != REPORT_TYPE_KEY:
        raise ValueError(
            "report_type_key inválido para "
            "ventas_nuevos_socios_detalle."
        )

    if snapshot_kind != SNAPSHOT_KIND:
        raise ValueError(
            "snapshot_kind inválido para "
            "ventas_nuevos_socios_detalle."
        )

    if date_to != business_date:
        raise ValueError(
            "date_to debe coincidir con business_date."
        )

    if date_from != business_date.replace(day=1):
        raise ValueError(
            "date_from debe ser el primer día del mes."
        )

    incoming_captured_at = _aware_utc(
        captured_at,
        field_name="captured_at",
    )

    incoming_valid = int(row_count_valid)
    incoming_rejected = int(row_count_rejected)

    if incoming_valid < 0 or incoming_rejected < 0:
        raise ValueError(
            "Los conteos de filas no pueden ser negativos."
        )

    if existing_canonical_snapshot is None:
        return {
            "is_canonical": True,
            "replace_existing_canonical": False,
            "reason": "first_snapshot_for_business_date",
        }

    existing_valid = int(
        getattr(
            existing_canonical_snapshot,
            "row_count_valid",
            0,
        )
        or 0
    )

    existing_rejected = int(
        getattr(
            existing_canonical_snapshot,
            "row_count_rejected",
            0,
        )
        or 0
    )

    existing_captured_at = _existing_datetime(
        existing_canonical_snapshot
    )

    incoming_is_better = (
        incoming_rejected < existing_rejected
        or (
            incoming_rejected == existing_rejected
            and incoming_valid > existing_valid
        )
        or (
            incoming_rejected == existing_rejected
            and incoming_valid == existing_valid
            and incoming_captured_at
            > existing_captured_at
        )
    )

    if incoming_is_better:
        return {
            "is_canonical": True,
            "replace_existing_canonical": True,
            "reason": "better_snapshot_for_business_date",
        }

    return {
        "is_canonical": False,
        "replace_existing_canonical": False,
        "reason": "existing_canonical_kept",
    }
