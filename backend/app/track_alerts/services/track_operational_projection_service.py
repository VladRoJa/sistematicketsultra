from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any


OPERATIONAL_PROJECTION_METHOD = (
    "recent_valid_daily_average_7_calendar_days"
)
OPERATIONAL_PROJECTION_WINDOW_CALENDAR_DAYS = 7
OPERATIONAL_PROJECTION_MIN_VALID_DELTAS = 3

OPERATIONAL_PROJECTION_METRIC_KEYS = (
    "clientes_nuevos",
    "reactivaciones",
    "domiciliados",
    "bajas",
)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    return (
        value
        if isinstance(value, Decimal)
        else Decimal(str(value))
    )


def _decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None

def build_operational_projection(
    history: list[dict[str, Any]],
    *,
    metric_key: str,
    cutoff_date: date,
    actual_mtd: Any,
    benchmark: Any,
) -> dict[str, Any]:
    if metric_key not in OPERATIONAL_PROJECTION_METRIC_KEYS:
        raise ValueError(
            f"Métrica de proyección operacional no soportada: {metric_key!r}"
        )

    days_in_month = monthrange(cutoff_date.year, cutoff_date.month)[1]
    remaining_days = days_in_month - cutoff_date.day
    window_start = cutoff_date - timedelta(
        days=OPERATIONAL_PROJECTION_WINDOW_CALENDAR_DAYS - 1
    )
    month_start = cutoff_date.replace(day=1)
    valid_deltas: list[Decimal] = []

    for point in history:
        point_date = date.fromisoformat(str(point["track_date"]))
        if point_date < window_start or point_date > cutoff_date:
            continue

        daily_delta = _decimal(
            (point.get("metrics", {}).get(metric_key) or {}).get(
                "daily_delta"
            )
        )
        if daily_delta is None:
            continue

        is_consecutive = bool(point.get("is_consecutive_previous_date"))
        is_valid_first_day = (
            point_date == month_start
            and point.get("previous_track_date") is None
            and point.get("days_since_previous") is None
        )
        if is_consecutive or is_valid_first_day:
            valid_deltas.append(daily_delta)

    valid_daily_deltas = len(valid_deltas)
    recent_daily_average = (
        sum(valid_deltas, Decimal("0")) / Decimal(valid_daily_deltas)
        if valid_daily_deltas >= OPERATIONAL_PROJECTION_MIN_VALID_DELTAS
        else None
    )
    actual = _decimal(actual_mtd)
    result = {
        "status": "insufficient_history",
        "method": OPERATIONAL_PROJECTION_METHOD,
        "window_calendar_days": (
            OPERATIONAL_PROJECTION_WINDOW_CALENDAR_DAYS
        ),
        "valid_daily_deltas": valid_daily_deltas,
        "recent_daily_average": _decimal_string(recent_daily_average),
        "remaining_days": remaining_days,
        "projected_close": None,
        "projected_points": [],
    }

    if actual is None:
        return result
    if remaining_days > 0 and recent_daily_average is None:
        return result

    projected_close = (
        actual
        if remaining_days == 0
        else actual + recent_daily_average * Decimal(remaining_days)
    )
    result.update(
        {
            "status": "available",
            "projected_close": _decimal_string(projected_close),
            "projected_points": (
                [
                    {
                        "track_date": (
                            cutoff_date + timedelta(days=day_offset)
                        ).isoformat(),
                        "projected_mtd": _decimal_string(
                            actual
                            + recent_daily_average * Decimal(day_offset)
                        ),
                    }
                    for day_offset in range(remaining_days + 1)
                ]
                if remaining_days > 0
                else []
            ),
        }
    )

    benchmark_value = _decimal(benchmark)
    if metric_key == "bajas":
        result.update(
            {
                "projected_excess_units": _decimal_string(
                    max(projected_close - benchmark_value, Decimal("0"))
                    if benchmark_value is not None
                    else None
                ),
                "projected_remaining_margin": _decimal_string(
                    max(benchmark_value - projected_close, Decimal("0"))
                    if benchmark_value is not None
                    else None
                ),
                "projected_limit_usage_pct": _decimal_string(
                    projected_close / benchmark_value * Decimal("100")
                    if benchmark_value is not None and benchmark_value > 0
                    else None
                ),
            }
        )
    else:
        result.update(
            {
                "projected_gap_units": _decimal_string(
                    projected_close - benchmark_value
                    if benchmark_value is not None
                    else None
                ),
                "projected_compliance_pct": _decimal_string(
                    projected_close / benchmark_value * Decimal("100")
                    if benchmark_value is not None and benchmark_value > 0
                    else None
                ),
            }
        )

    return result


