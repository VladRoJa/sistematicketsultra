from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Mapping, Sequence

from app.warehouse.services.track_bajas_forecast_service import (
    BAJAS_FORECAST_METHOD,
)


RECENT_DAILY_AVERAGE_METHOD = (
    "recent_valid_daily_average_7_calendar_days"
)
RECENT_DAILY_AVERAGE_WINDOW_CALENDAR_DAYS = 7
RECENT_DAILY_AVERAGE_MIN_VALID_DELTAS = 3
RECENT_DAILY_AVERAGE_METRIC_KEYS = (
    "clientes_nuevos",
    "reactivaciones",
    "domiciliados",
    "bajas",
    "tienda",
)

OPERATIONAL_FORECAST_METRIC_KEYS = (
    "ingreso",
    "clientes_nuevos",
    "reactivaciones",
    "bajas",
    "tienda",
)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Los valores numéricos no pueden ser booleanos.")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def build_recent_daily_average_projection(
    history: list[dict[str, Any]],
    *,
    metric_key: str,
    cutoff_date: date,
    actual_mtd: Any,
    benchmark: Any,
) -> dict[str, Any]:
    if metric_key not in RECENT_DAILY_AVERAGE_METRIC_KEYS:
        raise ValueError(
            f"Métrica de proyección operacional no soportada: {metric_key!r}"
        )

    days_in_month = monthrange(cutoff_date.year, cutoff_date.month)[1]
    remaining_days = days_in_month - cutoff_date.day
    window_start = cutoff_date - timedelta(
        days=RECENT_DAILY_AVERAGE_WINDOW_CALENDAR_DAYS - 1
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
        if valid_daily_deltas >= RECENT_DAILY_AVERAGE_MIN_VALID_DELTAS
        else None
    )
    actual = _decimal(actual_mtd)
    result: dict[str, Any] = {
        "status": "insufficient_history",
        "method": RECENT_DAILY_AVERAGE_METHOD,
        "window_calendar_days": (
            RECENT_DAILY_AVERAGE_WINDOW_CALENDAR_DAYS
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


def build_bajas_historical_projection(
    *,
    actual_mtd: Any,
    monthly_limit: Any,
    cutoff_day: int,
    progress_curve: Mapping[str, Any],
) -> dict[str, Any]:
    actual = _decimal(actual_mtd)
    limit = _decimal(monthly_limit)
    point = (progress_curve.get("points") or {}).get(int(cutoff_day))

    result: dict[str, Any] = {
        "status": "insufficient_history",
        "method": BAJAS_FORECAST_METHOD,
        "projected_close": None,
        "historical_progress_pct": None,
        "historical_samples_count": 0,
        "projected_excess_units": None,
        "projected_remaining_margin": None,
        "projected_limit_usage_pct": None,
    }

    if actual is None:
        result["quality_issue"] = {
            "code": "missing_current_bajas",
            "message": "No existe baja real MTD para proyectar el cierre.",
        }
        return result

    if progress_curve.get("status") != "available" or point is None:
        result["quality_issue"] = {
            "code": "missing_historical_progress",
            "message": (
                "No existe mediana histórica de avance para el día de corte."
            ),
        }
        return result

    median = _decimal(point.get("median"))
    if median is None or median <= 0:
        result["quality_issue"] = {
            "code": "invalid_historical_progress",
            "message": "La mediana histórica de avance no es válida.",
        }
        return result

    projected_close = actual / median
    result.update(
        {
            "status": "available",
            "projected_close": _decimal_string(projected_close),
            "historical_progress_pct": _decimal_string(
                median * Decimal("100")
            ),
            "historical_samples_count": int(
                point.get("samples_count") or 0
            ),
            "quality_issue": None,
        }
    )

    if limit is not None:
        result["projected_excess_units"] = _decimal_string(
            max(projected_close - limit, Decimal("0"))
        )
        result["projected_remaining_margin"] = _decimal_string(
            max(limit - projected_close, Decimal("0"))
        )
        result["projected_limit_usage_pct"] = _decimal_string(
            projected_close / limit * Decimal("100")
            if limit > 0
            else None
        )

    return result


def _normalize_metric_forecast(
    *,
    metric_key: str,
    actual_mtd: Any,
    benchmark: Any,
    benchmark_kind: str,
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    actual = _decimal(actual_mtd)
    benchmark_value = _decimal(benchmark)
    projected_close = _decimal(projection.get("projected_close"))
    projected_gap = (
        projected_close - benchmark_value
        if projected_close is not None and benchmark_value is not None
        else None
    )

    result: dict[str, Any] = {
        "metric_key": metric_key,
        "actual_mtd": _decimal_string(actual),
        "projected_close": _decimal_string(projected_close),
        "benchmark": _decimal_string(benchmark_value),
        "benchmark_kind": benchmark_kind,
        "projected_gap": _decimal_string(projected_gap),
        "status": str(projection.get("status") or "insufficient_history"),
        "method": projection.get("method"),
        "projection": dict(projection),
    }

    if metric_key == "bajas":
        result["projected_excess"] = _decimal_string(
            max(projected_gap, Decimal("0"))
            if projected_gap is not None
            else None
        )
        result["projected_remaining_margin"] = _decimal_string(
            max(-projected_gap, Decimal("0"))
            if projected_gap is not None
            else None
        )

    return result


def build_branch_operational_forecast(
    *,
    track_date: date,
    history: list[dict[str, Any]],
    income_actual_mtd: Any,
    income_monthly_target: Any,
    income_projection: Mapping[str, Any],
    clientes_nuevos_actual_mtd: Any,
    clientes_nuevos_monthly_target: Any,
    reactivaciones_actual_mtd: Any,
    reactivaciones_monthly_target: Any,
    bajas_actual_mtd: Any,
    bajas_monthly_limit: Any,
    bajas_progress_curve: Mapping[str, Any],
    tienda_actual_mtd: Any,
    tienda_monthly_target: Any,
    bajas_cutoff_day: int | None = None,
) -> dict[str, Any]:
    clientes_projection = build_recent_daily_average_projection(
        history,
        metric_key="clientes_nuevos",
        cutoff_date=track_date,
        actual_mtd=clientes_nuevos_actual_mtd,
        benchmark=clientes_nuevos_monthly_target,
    )
    reactivaciones_projection = build_recent_daily_average_projection(
        history,
        metric_key="reactivaciones",
        cutoff_date=track_date,
        actual_mtd=reactivaciones_actual_mtd,
        benchmark=reactivaciones_monthly_target,
    )
    bajas_projection = build_bajas_historical_projection(
        actual_mtd=bajas_actual_mtd,
        monthly_limit=bajas_monthly_limit,
        cutoff_day=bajas_cutoff_day or track_date.day,
        progress_curve=bajas_progress_curve,
    )
    tienda_projection = build_recent_daily_average_projection(
        history,
        metric_key="tienda",
        cutoff_date=track_date,
        actual_mtd=tienda_actual_mtd,
        benchmark=tienda_monthly_target,
    )

    return {
        "track_date": track_date.isoformat(),
        "metrics": {
            "ingreso": _normalize_metric_forecast(
                metric_key="ingreso",
                actual_mtd=income_actual_mtd,
                benchmark=income_monthly_target,
                benchmark_kind="target",
                projection=income_projection,
            ),
            "clientes_nuevos": _normalize_metric_forecast(
                metric_key="clientes_nuevos",
                actual_mtd=clientes_nuevos_actual_mtd,
                benchmark=clientes_nuevos_monthly_target,
                benchmark_kind="target",
                projection=clientes_projection,
            ),
            "reactivaciones": _normalize_metric_forecast(
                metric_key="reactivaciones",
                actual_mtd=reactivaciones_actual_mtd,
                benchmark=reactivaciones_monthly_target,
                benchmark_kind="target",
                projection=reactivaciones_projection,
            ),
            "bajas": _normalize_metric_forecast(
                metric_key="bajas",
                actual_mtd=bajas_actual_mtd,
                benchmark=bajas_monthly_limit,
                benchmark_kind="limit",
                projection=bajas_projection,
            ),
            "tienda": _normalize_metric_forecast(
                metric_key="tienda",
                actual_mtd=tienda_actual_mtd,
                benchmark=tienda_monthly_target,
                benchmark_kind="target",
                projection=tienda_projection,
            ),
        },
    }


def _complete_sum(values: Sequence[Decimal | None]) -> Decimal | None:
    if any(value is None for value in values):
        return None
    return sum(
        (value for value in values if value is not None),
        Decimal("0"),
    )


def build_operational_forecast_scope_summary(
    branch_forecasts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    total_branches = len(branch_forecasts)
    metrics: dict[str, Any] = {}

    for metric_key in OPERATIONAL_FORECAST_METRIC_KEYS:
        branch_metrics = [
            (branch.get("metrics") or {}).get(metric_key) or {}
            for branch in branch_forecasts
        ]
        actual_values = [
            _decimal(metric.get("actual_mtd"))
            for metric in branch_metrics
        ]
        benchmark_values = [
            _decimal(metric.get("benchmark"))
            for metric in branch_metrics
        ]
        projected_values = [
            _decimal(metric.get("projected_close"))
            if metric.get("status") == "available"
            else None
            for metric in branch_metrics
        ]

        actual_mtd = _complete_sum(actual_values)
        benchmark = _complete_sum(benchmark_values)
        projected_close = _complete_sum(projected_values)
        projected_gap = (
            projected_close - benchmark
            if projected_close is not None and benchmark is not None
            else None
        )
        available_branches = sum(
            1
            for metric in branch_metrics
            if (
                metric.get("status") == "available"
                and _decimal(metric.get("projected_close")) is not None
            )
        )
        methods = sorted(
            {
                str(metric.get("method"))
                for metric in branch_metrics
                if metric.get("method")
            }
        )

        summary: dict[str, Any] = {
            "metric_key": metric_key,
            "actual_mtd": _decimal_string(actual_mtd),
            "projected_close": _decimal_string(projected_close),
            "benchmark": _decimal_string(benchmark),
            "benchmark_kind": (
                "limit" if metric_key == "bajas" else "target"
            ),
            "projected_gap": _decimal_string(projected_gap),
            "status": (
                "available"
                if total_branches > 0
                and available_branches == total_branches
                else "insufficient_history"
            ),
            "method": "sum_branch_operational_forecasts",
            "branch_methods": methods,
            "coverage": {
                "total_branches": total_branches,
                "actual_available_branches": sum(
                    value is not None for value in actual_values
                ),
                "benchmark_available_branches": sum(
                    value is not None for value in benchmark_values
                ),
                "projected_available_branches": available_branches,
                "unavailable_branches_count": (
                    total_branches - available_branches
                ),
            },
        }

        if metric_key == "bajas":
            summary["projected_excess"] = _decimal_string(
                max(projected_gap, Decimal("0"))
                if projected_gap is not None
                else None
            )
            summary["projected_remaining_margin"] = _decimal_string(
                max(-projected_gap, Decimal("0"))
                if projected_gap is not None
                else None
            )
            summary["projected_limit_usage_pct"] = _decimal_string(
                projected_close / benchmark * Decimal("100")
                if (
                    projected_close is not None
                    and benchmark is not None
                    and benchmark > 0
                )
                else None
            )
        else:
            summary["projected_compliance_pct"] = _decimal_string(
                projected_close / benchmark * Decimal("100")
                if (
                    projected_close is not None
                    and benchmark is not None
                    and benchmark > 0
                )
                else None
            )

        metrics[metric_key] = summary

    return {
        "status": (
            "available"
            if total_branches > 0
            and all(
                metric["status"] == "available"
                for metric in metrics.values()
            )
            else "partial"
        ),
        "total_branches": total_branches,
        "metrics": metrics,
    }
