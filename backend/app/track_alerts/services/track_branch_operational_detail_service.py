from __future__ import annotations

from calendar import monthrange
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable

from app.extensions import db
from app.models.warehouse import TrackDailyMartORM
from app.track_alerts.services.track_alert_region_rules_service import (
    resolve_current_track_region_for_branch_id,
)
from app.track_alerts.services.track_intelligence_access_service import (
    TrackIntelligenceAuthorizationError,
    resolve_track_intelligence_access,
)
from app.track_alerts.services.track_regional_pacing_service import (
    build_bajas_metric,
    build_clientes_nuevos_metric,
    build_domiciliados_metric,
    build_reactivaciones_metric,
    build_target_progress_metric,
)
from app.warehouse.services.track_daily_query_version_service import (
    PREFERRED_TRACK_VERSION_TYPES,
    get_track_local_today,
    resolve_preferred_track_daily_version,
)
from app.warehouse.services.track_forecast_center_service import (
    ForecastCenterAccess,
    ForecastCenterBranch,
    resolve_forecast_center_universe,
    select_forecast_center_scope,
)
from app.warehouse.services.track_forecast_service import (
    build_branch_income_projection_summary,
)


PACE_SEVERELY_BELOW_PCT = Decimal("80")
BAJAS_HIGH_LIMIT_USAGE_PCT = Decimal("80")
BAJAS_NEAR_LIMIT_USAGE_PCT = Decimal("90")
TREND_WINDOW_VALID_CUTS = 3
TREND_DEAD_BAND_PP = Decimal("2")
MAX_OPERATIONAL_RECOMMENDATIONS = 3
OPERATIONAL_PROJECTION_METHOD = (
    "recent_valid_daily_average_7_calendar_days"
)
OPERATIONAL_PROJECTION_WINDOW_CALENDAR_DAYS = 7
OPERATIONAL_PROJECTION_MIN_VALID_DELTAS = 3
ACTIVE_MEMBERS_PROJECTION_METHOD = (
    "remaining_operational_component_projections"
)

PACE_METRIC_KEYS = (
    "clientes_nuevos",
    "reactivaciones",
    "domiciliados",
)
DAILY_DELTA_METRIC_KEYS = (
    "clientes_nuevos",
    "reactivaciones",
    "bajas",
    "domiciliados",
    "ingreso",
    "usuarios",
    "socios_activos",
    "tienda",
)
OPERATIONAL_PROJECTION_METRIC_KEYS = (
    "clientes_nuevos",
    "reactivaciones",
    "domiciliados",
    "bajas",
)
CHART_COMPARISON_PERIOD_KEYS = (
    "current_month",
    "previous_month",
    "previous_year_same_month",
)
CHART_COMPARISON_METRIC_KEYS = (
    *OPERATIONAL_PROJECTION_METRIC_KEYS,
    "socios_activos",
)


class TrackBranchOperationalDetailDataError(RuntimeError):
    pass


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _income_value(row: TrackDailyMartORM) -> Decimal | None:
    value = row.ingreso_real_total_mtd
    if value is None:
        value = row.ingreso_real_mtd
    return _decimal(value)


def _pace_pct(metric: dict[str, Any]) -> Decimal | None:
    actual = _decimal(metric.get("actual_mtd"))
    expected = _decimal(metric.get("expected_mtd"))
    if actual is None or expected is None or expected <= 0:
        return None
    return actual / expected * Decimal("100")


def _build_pace_metric(
    *,
    metric_key: str,
    actual_mtd: Any,
    monthly_target: Any,
    cutoff_date: date,
) -> dict[str, Any]:
    if metric_key == "clientes_nuevos":
        result = build_clientes_nuevos_metric(
            actual_mtd=actual_mtd,
            monthly_target=monthly_target,
            cutoff_date=cutoff_date,
        ).to_dict()
    elif metric_key == "reactivaciones":
        result = build_reactivaciones_metric(
            actual_mtd=actual_mtd,
            monthly_target=monthly_target,
            cutoff_date=cutoff_date,
        ).to_dict()
    elif metric_key == "domiciliados":
        result = build_domiciliados_metric(
            actual_mtd=actual_mtd,
            monthly_target=monthly_target,
            cutoff_date=cutoff_date,
        ).to_dict()
    else:
        raise ValueError(f"Métrica de ritmo no soportada: {metric_key!r}")

    result["pace_pct"] = _decimal_string(_pace_pct(result))
    return result


def _build_bajas_operational_metric(
    *,
    actual_mtd: Any,
    monthly_limit: Any,
) -> dict[str, Any]:
    result = build_bajas_metric(
        actual_mtd=actual_mtd,
        monthly_limit=monthly_limit,
    ).to_dict()
    actual = _decimal(result.get("actual_mtd"))
    limit = _decimal(result.get("monthly_limit"))

    if actual is not None and limit is not None and limit > 0:
        usage = (actual / limit) * Decimal("100")

        if actual > limit:
            result["status"] = "LIMITE_EXCEDIDO"
        elif usage >= BAJAS_NEAR_LIMIT_USAGE_PCT:
            result["status"] = "CERCA_LIMITE"
        elif usage >= BAJAS_HIGH_LIMIT_USAGE_PCT:
            result["status"] = "CONSUMO_ALTO"
        else:
            result["status"] = "DENTRO_LIMITE"

        result["remaining_before_limit"] = _decimal_string(
            max(limit - actual, Decimal("0"))
        )
        result["excess_units"] = _decimal_string(
            max(actual - limit, Decimal("0"))
        )
    else:
        result["remaining_before_limit"] = None
        result["excess_units"] = None

    return result


def _build_target_metric(
    *,
    metric_key: str,
    actual_mtd: Any,
    monthly_target: Any,
) -> dict[str, Any]:
    result = build_target_progress_metric(
        metric_key=metric_key,
        actual_mtd=actual_mtd,
        monthly_target=monthly_target,
    ).to_dict()
    if result["status"] not in {"SIN_META", "DATOS_INSUFICIENTES"}:
        result["status"] = "AVAILABLE"
    return result


def _build_users_metric(row: TrackDailyMartORM) -> dict[str, Any]:
    start_month = _decimal(row.usuarios_inicio_mes)
    actual = _decimal(row.usuarios_activos_actual)
    projected = _decimal(row.proyeccion_usuarios_cierre_mes)
    m2 = _decimal(row.m2_sin_circulaciones)

    occupancy_actual = (
        actual / m2
        if actual is not None and m2 is not None and m2 > 0
        else None
    )
    occupancy_month_target = (
        projected / m2
        if projected is not None and m2 is not None and m2 > 0
        else None
    )
    compliance_pct = (
        (actual / projected) * Decimal("100")
        if actual is not None and projected is not None and projected > 0
        else None
    )

    return {
        "metric_key": "usuarios",
        "start_month": _decimal_string(start_month),
        "actual": _decimal_string(actual),
        "change_from_start": _decimal_string(
            actual - start_month
            if actual is not None and start_month is not None
            else None
        ),
        "projected_month_close": _decimal_string(projected),
        "compliance_pct": _decimal_string(compliance_pct),
        "occupancy_actual": _decimal_string(occupancy_actual),
        "occupancy_month_target": _decimal_string(
            occupancy_month_target
        ),
        "status": (
            "AVAILABLE"
            if actual is not None
            else "DATOS_INSUFICIENTES"
        ),
    }


def _build_active_members_metric(row: TrackDailyMartORM) -> dict[str, Any]:
    actual = _decimal(row.usuarios_activos_actual)

    return {
        "metric_key": "socios_activos",
        "start_month": None,
        "actual_mtd": _decimal_string(actual),
        "change_from_start": None,
        "status": (
            "AVAILABLE"
            if actual is not None
            else "DATOS_INSUFICIENTES"
        ),
    }


def _build_metrics(
    *,
    row: TrackDailyMartORM,
    cutoff_date: date,
) -> dict[str, dict[str, Any]]:
    income = _build_target_metric(
        metric_key="ingreso",
        actual_mtd=_income_value(row),
        monthly_target=row.meta_faycgo_mes,
    )
    income.update(
        {
            "base_mtd": _decimal_string(_decimal(row.ingreso_real_base_mtd)),
            "agregadoras_mtd": _decimal_string(
                _decimal(row.ingreso_real_agregadora_mtd)
            ),
        }
    )

    return {
        "clientes_nuevos": _build_pace_metric(
            metric_key="clientes_nuevos",
            actual_mtd=row.clientes_nuevos_real_mtd,
            monthly_target=row.meta_clientes_nuevos_mes,
            cutoff_date=cutoff_date,
        ),
        "reactivaciones": _build_pace_metric(
            metric_key="reactivaciones",
            actual_mtd=row.reactivaciones_real_mtd,
            monthly_target=row.meta_reactivaciones_mes,
            cutoff_date=cutoff_date,
        ),
        "bajas": _build_bajas_operational_metric(
            actual_mtd=row.bajas_reales_mtd,
            monthly_limit=row.meta_bajas_mes,
        ),
        "domiciliados": _build_pace_metric(
            metric_key="domiciliados",
            actual_mtd=row.nuevos_domiciliados_real_mtd,
            monthly_target=row.meta_nuevos_domiciliados_mes,
            cutoff_date=cutoff_date,
        ),
        "ingreso": income,
        "usuarios": _build_users_metric(row),
        "socios_activos": _build_active_members_metric(row),
        "tienda": _build_target_metric(
            metric_key="tienda",
            actual_mtd=row.venta_tienda_real_mtd,
            monthly_target=row.meta_venta_tienda_mes,
        ),
    }


def _metric_mtd_value(metric_key: str, metric: dict[str, Any]) -> Decimal | None:
    if metric_key == "usuarios":
        return _decimal(metric.get("actual"))
    return _decimal(metric.get("actual_mtd"))


def _add_daily_deltas(
    *,
    metrics: dict[str, dict[str, Any]],
    previous_metrics: dict[str, dict[str, Any]] | None,
) -> None:
    for metric_key in DAILY_DELTA_METRIC_KEYS:
        current_value = _metric_mtd_value(metric_key, metrics[metric_key])
        previous_value = (
            _metric_mtd_value(metric_key, previous_metrics[metric_key])
            if previous_metrics is not None
            else None
        )
        metrics[metric_key]["daily_delta"] = _decimal_string(
            current_value - previous_value
            if current_value is not None and previous_value is not None
            else None
        )


def _build_operational_projection(
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


def _build_active_members_projection(
    *,
    metrics: dict[str, dict[str, Any]],
    cutoff_date: date,
) -> dict[str, Any]:
    component_keys = (
        "clientes_nuevos",
        "reactivaciones",
        "bajas",
    )
    days_in_month = monthrange(cutoff_date.year, cutoff_date.month)[1]
    remaining_days = days_in_month - cutoff_date.day
    observed = _decimal(
        metrics.get("socios_activos", {}).get("actual_mtd")
    )
    components: dict[str, dict[str, str | None]] = {}
    missing_components: list[str] = []

    for metric_key in component_keys:
        metric = metrics.get(metric_key) or {}
        projection = metric.get("projection") or {}
        actual = _decimal(metric.get("actual_mtd"))
        projected_close = (
            _decimal(projection.get("projected_close"))
            if projection.get("status") == "available"
            else None
        )
        remaining_projected = (
            projected_close - actual
            if actual is not None and projected_close is not None
            else None
        )
        components[metric_key] = {
            "actual_mtd": _decimal_string(actual),
            "projected_close": _decimal_string(projected_close),
            "remaining_projected": _decimal_string(remaining_projected),
        }
        if remaining_projected is None:
            missing_components.append(metric_key)

    result: dict[str, Any] = {
        "status": "insufficient_data",
        "method": ACTIVE_MEMBERS_PROJECTION_METHOD,
        "remaining_days": remaining_days,
        "projected_close": None,
        "projected_points": [],
        "components": components,
        "missing_components": missing_components,
    }

    if observed is None:
        result["missing_components"] = [
            "socios_activos",
            *missing_components,
        ]
        return result

    if remaining_days == 0:
        result.update(
            {
                "status": "available",
                "projected_close": _decimal_string(observed),
                "missing_components": [],
            }
        )
        return result

    if missing_components:
        return result

    remaining_by_component = {
        metric_key: _decimal(
            components[metric_key]["remaining_projected"]
        )
        for metric_key in component_keys
    }
    projected_close = (
        observed
        + remaining_by_component["clientes_nuevos"]
        + remaining_by_component["reactivaciones"]
        - remaining_by_component["bajas"]
    )

    projected_point_maps: dict[str, dict[str, Decimal]] = {}
    for metric_key in component_keys:
        projection = metrics[metric_key]["projection"]
        projected_point_maps[metric_key] = {
            str(point["track_date"]): projected_value
            for point in projection.get("projected_points", [])
            if (projected_value := _decimal(point.get("projected_mtd")))
            is not None
        }

    common_dates = set(projected_point_maps[component_keys[0]])
    for metric_key in component_keys[1:]:
        common_dates.intersection_update(projected_point_maps[metric_key])

    projected_points = []
    for track_date in sorted(common_dates):
        clientes_remaining = (
            projected_point_maps["clientes_nuevos"][track_date]
            - _decimal(metrics["clientes_nuevos"]["actual_mtd"])
        )
        reactivaciones_remaining = (
            projected_point_maps["reactivaciones"][track_date]
            - _decimal(metrics["reactivaciones"]["actual_mtd"])
        )
        bajas_remaining = (
            projected_point_maps["bajas"][track_date]
            - _decimal(metrics["bajas"]["actual_mtd"])
        )
        projected_points.append(
            {
                "track_date": track_date,
                "projected_mtd": _decimal_string(
                    observed
                    + clientes_remaining
                    + reactivaciones_remaining
                    - bajas_remaining
                ),
            }
        )

    result.update(
        {
            "status": "available",
            "projected_close": _decimal_string(projected_close),
            "projected_points": projected_points,
        }
    )
    return result


def _trend_value(
    point: dict[str, Any],
    metric_key: str,
) -> Decimal | None:
    metric = point["metrics"].get(metric_key) or {}
    if metric_key in PACE_METRIC_KEYS:
        return _decimal(metric.get("pace_pct"))
    if metric_key == "bajas":
        return _decimal(metric.get("limit_usage_pct"))
    return None


def _build_metric_trend(
    history: list[dict[str, Any]],
    *,
    metric_key: str,
) -> dict[str, Any]:
    valid_points = [
        point
        for point in history
        if _trend_value(point, metric_key) is not None
    ]
    window = valid_points[-TREND_WINDOW_VALID_CUTS:]
    if len(window) < TREND_WINDOW_VALID_CUTS:
        return {
            "trend": "INSUFFICIENT_DATA",
            "trend_net_change_pp": None,
            "trend_start_date": None,
        }

    first_value = _trend_value(window[0], metric_key)
    last_value = _trend_value(window[-1], metric_key)
    if first_value is None or last_value is None:
        raise TrackBranchOperationalDetailDataError(
            "La ventana de tendencia contiene valores no comparables."
        )
    net_change = last_value - first_value

    if metric_key == "bajas":
        if net_change >= TREND_DEAD_BAND_PP:
            trend = "DETERIORATING"
        elif net_change <= -TREND_DEAD_BAND_PP:
            trend = "IMPROVING"
        else:
            trend = "STABLE"
    elif net_change <= -TREND_DEAD_BAND_PP:
        trend = "DETERIORATING"
    elif net_change >= TREND_DEAD_BAND_PP:
        trend = "IMPROVING"
    else:
        trend = "STABLE"

    return {
        "trend": trend,
        "trend_net_change_pp": _decimal_string(net_change),
        "trend_start_date": (
            window[0]["track_date"]
            if trend in {"DETERIORATING", "IMPROVING"}
            else None
        ),
    }


def _change_direction(
    *,
    metric_key: str,
    net_change: Decimal | None,
) -> str:
    if net_change is None:
        return "INSUFFICIENT_DATA"
    if metric_key not in (*PACE_METRIC_KEYS, "bajas"):
        return "NOT_APPLICABLE"

    if -TREND_DEAD_BAND_PP < net_change < TREND_DEAD_BAND_PP:
        return "STABLE"
    if metric_key == "bajas":
        return "WORSENING" if net_change >= TREND_DEAD_BAND_PP else "IMPROVING"
    return "IMPROVING" if net_change >= TREND_DEAD_BAND_PP else "WORSENING"


def _build_change_vs_previous(
    history: list[dict[str, Any]],
    *,
    current_track_date: date,
) -> dict[str, Any]:
    if not history or history[-1]["track_date"] != current_track_date.isoformat():
        return {
            "previous_track_date": None,
            "days_since_previous": None,
            "is_consecutive_previous_date": False,
            "metrics": {},
        }

    current = history[-1]
    if len(history) < 2:
        return {
            "previous_track_date": None,
            "days_since_previous": None,
            "is_consecutive_previous_date": False,
            "metrics": {},
        }

    previous = history[-2]
    changes: dict[str, Any] = {}
    for metric_key in DAILY_DELTA_METRIC_KEYS:
        current_metric = current["metrics"][metric_key]
        previous_metric = previous["metrics"][metric_key]
        comparison_field = (
            "limit_usage_pct"
            if metric_key == "bajas"
            else "pace_pct"
            if metric_key in PACE_METRIC_KEYS
            else "compliance_pct"
            if metric_key in {"ingreso", "tienda"}
            else None
        )
        previous_comparison = (
            _decimal(previous_metric.get(comparison_field))
            if comparison_field
            else None
        )
        current_comparison = (
            _decimal(current_metric.get(comparison_field))
            if comparison_field
            else None
        )
        comparison_delta = (
            current_comparison - previous_comparison
            if current_comparison is not None and previous_comparison is not None
            else None
        )
        changes[metric_key] = {
            "actual_delta": current_metric.get("daily_delta"),
            "comparison_field": comparison_field,
            "comparison_previous": _decimal_string(previous_comparison),
            "comparison_current": _decimal_string(current_comparison),
            "comparison_delta_pp": _decimal_string(comparison_delta),
            "direction": _change_direction(
                metric_key=metric_key,
                net_change=comparison_delta,
            ),
        }

    return {
        "previous_track_date": previous["track_date"],
        "days_since_previous": current["days_since_previous"],
        "is_consecutive_previous_date": current[
            "is_consecutive_previous_date"
        ],
        "metrics": changes,
    }


def _signal(
    *,
    signal_key: str,
    metric_key: str,
    severity: str,
    title: str,
    summary: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "signal_key": signal_key,
        "metric_key": metric_key,
        "severity": severity,
        "title": title,
        "summary": summary,
        "evidence": evidence,
        "status": "active",
    }


def _build_pace_signals(
    *,
    metric_key: str,
    metric: dict[str, Any],
) -> list[dict[str, Any]]:
    pace = _decimal(metric.get("pace_pct"))
    if pace is None:
        return []

    label = {
        "clientes_nuevos": "Clientes nuevos",
        "reactivaciones": "Reactivaciones",
        "domiciliados": "Domiciliados",
    }[metric_key]
    signals: list[dict[str, Any]] = []
    evidence = {
        "pace_pct": _decimal_string(pace),
        "threshold_pct": _decimal_string(PACE_SEVERELY_BELOW_PCT),
        "trend": metric.get("trend"),
        "trend_net_change_pp": metric.get("trend_net_change_pp"),
    }

    if pace < PACE_SEVERELY_BELOW_PCT:
        signals.append(
            _signal(
                signal_key=f"{metric_key}_severely_below_pace",
                metric_key=metric_key,
                severity="critical",
                title=f"{label} severamente debajo del ritmo",
                summary=f"La sucursal opera al {pace:.1f}% del ritmo esperado.",
                evidence=evidence,
            )
        )
    elif pace < Decimal("100"):
        signals.append(
            _signal(
                signal_key=f"{metric_key}_below_pace",
                metric_key=metric_key,
                severity="warning",
                title=f"{label} debajo del ritmo",
                summary=f"La sucursal opera al {pace:.1f}% del ritmo esperado.",
                evidence=evidence,
            )
        )

    if metric.get("trend") == "DETERIORATING":
        signals.append(
            _signal(
                signal_key=f"{metric_key}_recent_slowdown",
                metric_key=metric_key,
                severity="warning",
                title=f"{label} con deterioro reciente",
                summary=(
                    "El ritmo perdió al menos 2 puntos porcentuales en los "
                    "últimos tres cortes válidos."
                ),
                evidence=evidence,
            )
        )
    elif metric.get("trend") == "IMPROVING" and pace < Decimal("100"):
        signals.append(
            _signal(
                signal_key=f"{metric_key}_recovering",
                metric_key=metric_key,
                severity="info",
                title=f"{label} en recuperación",
                summary=(
                    "Continúa debajo del ritmo esperado, pero mejoró al menos "
                    "2 puntos porcentuales en los últimos tres cortes válidos."
                ),
                evidence=evidence,
            )
        )

    return signals


def _build_bajas_signals(metric: dict[str, Any]) -> list[dict[str, Any]]:
    usage = _decimal(metric.get("limit_usage_pct"))
    if usage is None:
        return []

    evidence = {
        "limit_usage_pct": _decimal_string(usage),
        "high_usage_threshold_pct": _decimal_string(
            BAJAS_HIGH_LIMIT_USAGE_PCT
        ),
        "near_limit_threshold_pct": _decimal_string(
            BAJAS_NEAR_LIMIT_USAGE_PCT
        ),
        "trend": metric.get("trend"),
        "trend_net_change_pp": metric.get("trend_net_change_pp"),
    }
    signals: list[dict[str, Any]] = []

    if usage > Decimal("100"):
        signals.append(
            _signal(
                signal_key="bajas_limit_exceeded",
                metric_key="bajas",
                severity="critical",
                title="Límite de bajas excedido",
                summary=f"Las bajas consumieron {usage:.1f}% del límite mensual.",
                evidence=evidence,
            )
        )
    elif usage >= BAJAS_NEAR_LIMIT_USAGE_PCT:
        signals.append(
            _signal(
                signal_key="bajas_near_limit",
                metric_key="bajas",
                severity="warning",
                title="Bajas cerca del límite",
                summary=f"Las bajas consumieron {usage:.1f}% del límite mensual.",
                evidence=evidence,
            )
        )
    elif usage >= BAJAS_HIGH_LIMIT_USAGE_PCT:
        signals.append(
            _signal(
                signal_key="bajas_high_limit_usage",
                metric_key="bajas",
                severity="warning",
                title="Consumo alto del límite de bajas",
                summary=f"Las bajas consumieron {usage:.1f}% del límite mensual.",
                evidence=evidence,
            )
        )

    if metric.get("trend") == "DETERIORATING":
        signals.append(
            _signal(
                signal_key="bajas_recent_acceleration",
                metric_key="bajas",
                severity="warning",
                title="Bajas con aceleración reciente",
                summary=(
                    "El consumo del límite aumentó al menos 2 puntos "
                    "porcentuales en los últimos tres cortes válidos."
                ),
                evidence=evidence,
            )
        )

    return signals


def _build_income_signals(metric: dict[str, Any]) -> list[dict[str, Any]]:
    projection = metric.get("projection") or {}
    target = _decimal(metric.get("monthly_target"))
    projected_close = _decimal(projection.get("projected_close"))

    if projection.get("status") != "available" or projected_close is None:
        return [
            _signal(
                signal_key="projection_unavailable",
                metric_key="ingreso",
                severity="info",
                title="Proyección de ingreso no disponible",
                summary=(
                    "La historia comparable no es suficiente para inferir "
                    "el cierre mensual de ingreso."
                ),
                evidence={
                    "projection_status": projection.get("status"),
                    "quality_issue": projection.get("quality_issue"),
                },
            )
        ]

    if target is None or target <= 0:
        return []

    evidence = {
        "projected_close": _decimal_string(projected_close),
        "monthly_target": _decimal_string(target),
        "projection_method": projection.get("method"),
    }
    if projected_close < target:
        return [
            _signal(
                signal_key="ingreso_projection_below_target",
                metric_key="ingreso",
                severity="warning",
                title="Proyección de ingreso debajo de la meta",
                summary=(
                    "La proyección histórica de cierre permanece debajo de "
                    "la meta mensual."
                ),
                evidence=evidence,
            )
        ]

    return [
        _signal(
            signal_key="ingreso_projection_above_target",
            metric_key="ingreso",
            severity="success",
            title="Proyección de ingreso en meta",
            summary=(
                "La proyección histórica de cierre alcanza o supera la meta mensual."
            ),
            evidence=evidence,
        )
    ]


def _build_operational_signals(
    metrics: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if metrics is None:
        return []
    signals: list[dict[str, Any]] = []
    for metric_key in PACE_METRIC_KEYS:
        signals.extend(
            _build_pace_signals(
                metric_key=metric_key,
                metric=metrics[metric_key],
            )
        )
    signals.extend(_build_bajas_signals(metrics["bajas"]))
    signals.extend(_build_income_signals(metrics["ingreso"]))
    return signals


def _signal_keys_for_metric(
    signals: Iterable[dict[str, Any]],
    *,
    metric_key: str,
) -> list[str]:
    return [
        str(signal["signal_key"])
        for signal in signals
        if signal.get("metric_key") == metric_key
    ]


def _build_pace_operational_summary(
    *,
    metric_key: str,
    metric: dict[str, Any],
    signals: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    pace = _decimal(metric.get("pace_pct"))
    actual = _decimal(metric.get("actual_mtd"))
    target = _decimal(metric.get("monthly_target"))
    projection = metric.get("projection") or {}
    projected_close = _decimal(projection.get("projected_close"))
    remaining_days = int(projection.get("remaining_days") or 0)

    projected_below_target = (
        projected_close is not None
        and target is not None
        and target > 0
        and projected_close < target
    )
    below_pace = pace is not None and pace < Decimal("100")

    # Una tendencia negativa aislada no debe convertirse en tarjeta ejecutiva
    # si el KPI conserva ritmo sano y la proyección no queda debajo de meta.
    if not below_pace and not projected_below_target:
        return None

    required_daily_average = (
        max(target - actual, Decimal("0")) / Decimal(remaining_days)
        if (
            target is not None
            and actual is not None
            and remaining_days > 0
        )
        else None
    )

    severity = (
        "critical"
        if pace is not None and pace < PACE_SEVERELY_BELOW_PCT
        else "warning"
    )

    if remaining_days == 0:
        title = "El mes cerró por debajo de la meta"
    else:
        title = (
            "El ritmo actual no alcanza para cerrar la meta"
            if projected_below_target
            else "Opera debajo del ritmo esperado"
        )

    return {
        "metric_key": metric_key,
        "severity": severity,
        "title": title,
        "actual_mtd": _decimal_string(actual),
        "today_delta": metric.get("daily_delta"),
        "pace_pct": _decimal_string(pace),
        "recent_daily_average": projection.get("recent_daily_average"),
        "required_daily_average": _decimal_string(required_daily_average),
        "remaining_days": remaining_days,
        "projected_close": projection.get("projected_close"),
        "benchmark": _decimal_string(target),
        "projected_gap_units": projection.get("projected_gap_units"),
        "projected_compliance_pct": projection.get(
            "projected_compliance_pct"
        ),
        "trend": metric.get("trend"),
        "source_signal_keys": _signal_keys_for_metric(
            signals,
            metric_key=metric_key,
        ),
    }


def _build_bajas_operational_summary(
    *,
    metric: dict[str, Any],
    signals: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    usage = _decimal(metric.get("limit_usage_pct"))
    actual = _decimal(metric.get("actual_mtd"))
    limit = _decimal(metric.get("monthly_limit"))
    projection = metric.get("projection") or {}
    projected_close = _decimal(projection.get("projected_close"))
    remaining_days = int(projection.get("remaining_days") or 0)

    current_attention = (
        usage is not None
        and usage >= BAJAS_HIGH_LIMIT_USAGE_PCT
    )
    projected_exceeded = (
        projected_close is not None
        and limit is not None
        and limit > 0
        and projected_close > limit
    )

    # La aceleración reciente por sí sola queda como evidencia técnica.
    # La tarjeta ejecutiva aparece cuando existe riesgo actual o proyectado.
    if not current_attention and not projected_exceeded:
        return None

    if remaining_days == 0:
        if usage is not None and usage > Decimal("100"):
            severity = "critical"
            title = "El mes cerró por encima del límite de bajas"
        elif usage is not None and usage >= BAJAS_NEAR_LIMIT_USAGE_PCT:
            severity = "warning"
            title = "El mes cerró cerca del límite de bajas"
        else:
            severity = "warning"
            title = "El mes cerró dentro del límite, con consumo alto"
    elif usage is not None and usage > Decimal("100"):
        severity = "critical"
        title = "El límite mensual de bajas ya fue excedido"
    elif projected_exceeded:
        severity = "warning"
        title = "La tendencia actual proyecta exceder el límite"
    elif usage is not None and usage >= BAJAS_NEAR_LIMIT_USAGE_PCT:
        severity = "warning"
        title = "Las bajas están cerca del límite mensual"
    else:
        severity = "warning"
        title = "El consumo de bajas requiere atención"

    return {
        "metric_key": "bajas",
        "severity": severity,
        "title": title,
        "actual_mtd": _decimal_string(actual),
        "today_delta": metric.get("daily_delta"),
        "limit_usage_pct": _decimal_string(usage),
        "recent_daily_average": projection.get("recent_daily_average"),
        "remaining_days": int(projection.get("remaining_days") or 0),
        "projected_close": projection.get("projected_close"),
        "benchmark": _decimal_string(limit),
        "projected_excess_units": projection.get(
            "projected_excess_units"
        ),
        "projected_remaining_margin": projection.get(
            "projected_remaining_margin"
        ),
        "projected_limit_usage_pct": projection.get(
            "projected_limit_usage_pct"
        ),
        "trend": metric.get("trend"),
        "source_signal_keys": _signal_keys_for_metric(
            signals,
            metric_key="bajas",
        ),
    }


def _build_income_operational_summary(
    *,
    metric: dict[str, Any],
    signals: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    target = _decimal(metric.get("monthly_target"))
    actual = _decimal(metric.get("actual_mtd"))
    projection = metric.get("projection") or {}
    projected_close = _decimal(projection.get("projected_close"))

    if (
        projection.get("status") != "available"
        or projected_close is None
        or target is None
        or target <= 0
        or projected_close >= target
    ):
        return None

    projected_gap = projected_close - target

    return {
        "metric_key": "ingreso",
        "severity": "warning",
        "title": "El cierre proyectado queda debajo de la meta",
        "actual_mtd": _decimal_string(actual),
        "today_delta": metric.get("daily_delta"),
        "projected_close": _decimal_string(projected_close),
        "benchmark": _decimal_string(target),
        "projected_gap_units": _decimal_string(projected_gap),
        "projected_compliance_pct": _decimal_string(
            projected_close / target * Decimal("100")
        ),
        "projection_method": projection.get("method"),
        "source_signal_keys": _signal_keys_for_metric(
            signals,
            metric_key="ingreso",
        ),
    }


def _build_operational_summaries(
    *,
    metrics: dict[str, dict[str, Any]] | None,
    signals: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    if metrics is None:
        return []

    signal_rows = list(signals)
    summaries: list[dict[str, Any]] = []

    for metric_key in PACE_METRIC_KEYS:
        summary = _build_pace_operational_summary(
            metric_key=metric_key,
            metric=metrics[metric_key],
            signals=signal_rows,
        )
        if summary is not None:
            summaries.append(summary)

    bajas_summary = _build_bajas_operational_summary(
        metric=metrics["bajas"],
        signals=signal_rows,
    )
    if bajas_summary is not None:
        summaries.append(bajas_summary)

    income_summary = _build_income_operational_summary(
        metric=metrics["ingreso"],
        signals=signal_rows,
    )
    if income_summary is not None:
        summaries.append(income_summary)

    return summaries


def _has_signal(signals: Iterable[dict[str, Any]], signal_key: str) -> bool:
    return any(signal.get("signal_key") == signal_key for signal in signals)


def _pace_is_healthy(metrics: dict[str, Any], metric_key: str) -> bool:
    pace = _decimal(metrics[metric_key].get("pace_pct"))
    return pace is not None and pace >= Decimal("100")


def _pace_is_lagging(metrics: dict[str, Any], metric_key: str) -> bool:
    pace = _decimal(metrics[metric_key].get("pace_pct"))
    return pace is not None and pace < Decimal("100")


def _build_cross_metric_diagnosis(
    *,
    metrics: dict[str, dict[str, Any]] | None,
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    if metrics is None:
        return {
            "overall_status": "insufficient_data",
            "severity": "info",
            "headline": "Sin datos suficientes para diagnosticar",
            "summary": "No existe un corte operativo válido para la fecha solicitada.",
            "primary_blocker": None,
            "supporting_signals": [],
        }

    pace_values = [
        _decimal(metrics[key].get("pace_pct")) for key in PACE_METRIC_KEYS
    ]
    if all(value is None for value in pace_values):
        return {
            "overall_status": "insufficient_data",
            "severity": "info",
            "headline": "Datos comerciales insuficientes",
            "summary": "No hay métricas de ritmo comparables para este corte.",
            "primary_blocker": None,
            "supporting_signals": [
                signal["signal_key"] for signal in signals
            ],
        }

    clientes_healthy = _pace_is_healthy(metrics, "clientes_nuevos")
    clientes_lagging = _pace_is_lagging(metrics, "clientes_nuevos")
    reactivaciones_healthy = _pace_is_healthy(metrics, "reactivaciones")
    reactivaciones_lagging = _pace_is_lagging(metrics, "reactivaciones")
    domiciliados_healthy = _pace_is_healthy(metrics, "domiciliados")
    domiciliados_lagging = _pace_is_lagging(metrics, "domiciliados")
    bajas_usage = _decimal(metrics["bajas"].get("limit_usage_pct"))
    bajas_risk = (
        bajas_usage is not None
        and bajas_usage >= BAJAS_NEAR_LIMIT_USAGE_PCT
    )
    users_change = _decimal(metrics["usuarios"].get("change_from_start"))
    users_down = users_change is not None and users_change < 0
    income_below = _has_signal(signals, "ingreso_projection_below_target")
    supporting = [
        signal["signal_key"]
        for signal in signals
        if signal["severity"] in {"warning", "critical"}
    ]

    if clientes_lagging and reactivaciones_lagging and domiciliados_lagging:
        return {
            "overall_status": "critical",
            "severity": "critical",
            "headline": "Deterioro comercial general",
            "summary": (
                "Clientes nuevos, reactivaciones y domiciliados operan debajo "
                "del ritmo esperado; conviene revisar el proceso comercial completo."
            ),
            "primary_blocker": "comercial_general",
            "supporting_signals": supporting,
        }

    if bajas_risk and users_down:
        return {
            "overall_status": "attention_required",
            "severity": "critical" if bajas_usage and bajas_usage > 100 else "warning",
            "headline": "Patrón consistente con riesgo de retención",
            "summary": (
                "Las bajas están cerca o arriba del límite y los usuarios activos "
                "disminuyeron desde el inicio del mes."
            ),
            "primary_blocker": "retencion",
            "supporting_signals": supporting,
        }

    if clientes_healthy and domiciliados_lagging:
        return {
            "overall_status": "attention_required",
            "severity": "warning",
            "headline": "Posible bloqueo en domiciliación",
            "summary": (
                "Clientes nuevos mantiene ritmo sano, pero domiciliados está "
                "rezagado; el patrón es consistente con una brecha de conversión."
            ),
            "primary_blocker": "domiciliados",
            "supporting_signals": supporting,
        }

    if clientes_lagging and reactivaciones_healthy:
        return {
            "overall_status": "attention_required",
            "severity": "warning",
            "headline": "Posible bloqueo en captación",
            "summary": (
                "Reactivaciones mantiene ritmo sano mientras clientes nuevos está "
                "rezagado; conviene revisar captación y conversión comercial."
            ),
            "primary_blocker": "clientes_nuevos",
            "supporting_signals": supporting,
        }

    if income_below and clientes_healthy:
        return {
            "overall_status": "attention_required",
            "severity": "warning",
            "headline": "Ingreso proyectado debajo de meta",
            "summary": (
                "La captación mantiene ritmo sano, pero la proyección histórica de "
                "ingreso queda debajo de meta; conviene revisar mezcla de ingresos."
            ),
            "primary_blocker": "ingreso",
            "supporting_signals": supporting,
        }

    if clientes_lagging and domiciliados_lagging:
        return {
            "overall_status": "attention_required",
            "severity": "warning",
            "headline": "Captación y domiciliación requieren atención",
            "summary": (
                "El patrón es consistente con un problema comercial general o "
                "insuficiencia de cierres; conviene revisar el embudo completo."
            ),
            "primary_blocker": "comercial_general",
            "supporting_signals": supporting,
        }

    all_commercial_healthy = (
        clientes_healthy and reactivaciones_healthy and domiciliados_healthy
    )
    bajas_healthy = bajas_usage is not None and bajas_usage < BAJAS_HIGH_LIMIT_USAGE_PCT
    if all_commercial_healthy and bajas_healthy and not income_below:
        return {
            "overall_status": "healthy",
            "severity": "success",
            "headline": "Operación comercial estable",
            "summary": (
                "Los KPI comerciales mantienen el ritmo y las bajas permanecen "
                "debajo del umbral de atención."
            ),
            "primary_blocker": None,
            "supporting_signals": supporting,
        }

    if any(signal["severity"] == "critical" for signal in signals):
        overall_status = "critical"
        severity = "critical"
    elif supporting:
        overall_status = "attention_required"
        severity = "warning"
    else:
        overall_status = "watch"
        severity = "info"

    return {
        "overall_status": overall_status,
        "severity": severity,
        "headline": "Seguimiento operativo requerido",
        "summary": (
            "No existe evidencia suficiente para atribuir una causa única; "
            "conviene revisar las señales activas del corte."
        ),
        "primary_blocker": None,
        "supporting_signals": supporting,
    }


def _operational_display_number(value: Any) -> str | None:
    numeric = _decimal(value)
    if numeric is None:
        return None

    if numeric == numeric.to_integral_value():
        return f"{numeric:.0f}"

    return f"{numeric:.1f}"


def _operational_summary_map(
    operational_summaries: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(summary["metric_key"]): summary
        for summary in operational_summaries
        if summary.get("metric_key")
    }


def _pace_recommendation_reason(
    *,
    label: str,
    summary: dict[str, Any] | None,
    fallback: str,
) -> str:
    if summary is None:
        return fallback

    projected_close = _operational_display_number(
        summary.get("projected_close")
    )
    benchmark = _operational_display_number(summary.get("benchmark"))
    required = _operational_display_number(
        summary.get("required_daily_average")
    )
    gap = _decimal(summary.get("projected_gap_units"))
    remaining_days = int(summary.get("remaining_days") or 0)

    if remaining_days == 0:
        if projected_close is None or benchmark is None:
            return fallback

        if gap is not None and gap < 0:
            return (
                f"{label} cerró en {projected_close} de {benchmark}; "
                f"faltaron {_operational_display_number(abs(gap))}."
            )

        return f"{label} cerró en {projected_close} de {benchmark}."

    if required is not None:
        return (
            f"Para llegar a la meta se necesitan "
            f"{required} {label.lower()} por día."
        )

    return fallback


def _bajas_recommendation_reason(
    *,
    summary: dict[str, Any] | None,
    fallback: str,
) -> str:
    if summary is None:
        return fallback

    projected_close = _operational_display_number(
        summary.get("projected_close")
    )
    benchmark = _operational_display_number(summary.get("benchmark"))
    excess = _decimal(summary.get("projected_excess_units"))
    remaining_days = int(summary.get("remaining_days") or 0)

    if projected_close is None or benchmark is None:
        return fallback

    if remaining_days == 0:
        reason = (
            f"El mes cerró en {projected_close} bajas "
            f"con un límite de {benchmark}."
        )
    else:
        reason = (
            f"Si continúa el ritmo actual, las bajas podrían cerrar "
            f"en {projected_close} con un límite de {benchmark}."
        )

    if excess is not None and excess > 0:
        reason += (
            f" Serían {_operational_display_number(excess)} "
            "arriba del límite."
        )

    return reason


def _bajas_recommendation_actions(
    *,
    summary: dict[str, Any] | None,
    fallback: list[str],
) -> list[str]:
    if summary is None:
        return list(fallback)[:3]

    actual = _decimal(summary.get("actual_mtd"))
    limit = _decimal(summary.get("benchmark"))
    recent_average = _decimal(summary.get("recent_daily_average"))
    remaining_days = int(summary.get("remaining_days") or 0)

    if (
        actual is None
        or limit is None
        or remaining_days <= 0
    ):
        return list(fallback)[:3]

    remaining_margin = max(limit - actual, Decimal("0"))
    max_daily_increase = (
        remaining_margin / Decimal(remaining_days)
    )

    actions = [
        (
            "Para no pasar el límite, el total de bajas no debería "
            f"aumentar más de "
            f"{_operational_display_number(max_daily_increase)} "
            f"por día durante los {remaining_days} días restantes."
        ),
    ]

    if (
        recent_average is not None
        and recent_average > max_daily_increase
    ):
        reduction_needed = recent_average - max_daily_increase
        actions.append(
            (
                f"El promedio reciente es "
                f"{_operational_display_number(recent_average)} por día; "
                f"hay que reducirlo aproximadamente "
                f"{_operational_display_number(reduction_needed)} "
                "por día."
            )
        )

    actions.extend(fallback)

    return actions[:3]


def _income_recommendation_reason(
    *,
    summary: dict[str, Any] | None,
    fallback: str,
) -> str:
    if summary is None:
        return fallback

    projected_close = _operational_display_number(
        summary.get("projected_close")
    )
    benchmark = _operational_display_number(summary.get("benchmark"))

    if projected_close is None or benchmark is None:
        return fallback

    return (
        f"El ingreso proyectado es {projected_close} "
        f"frente a una meta de {benchmark}."
    )


def _commercial_general_reason(
    *,
    summaries_by_metric: dict[str, dict[str, Any]],
    fallback: str,
) -> str:
    labels = {
        "clientes_nuevos": "Clientes nuevos",
        "reactivaciones": "reactivaciones",
        "domiciliados": "domiciliados",
    }

    active_labels = [
        labels[metric_key]
        for metric_key in (
            "clientes_nuevos",
            "reactivaciones",
            "domiciliados",
        )
        if metric_key in summaries_by_metric
    ]

    if not active_labels:
        return fallback

    if len(active_labels) == 1:
        return f"{active_labels[0]} necesita recuperarse."

    if len(active_labels) == 2:
        return (
            f"{active_labels[0]} y {active_labels[1]} "
            "necesitan recuperarse."
        )

    return (
        f"{active_labels[0]}, {active_labels[1]} y "
        f"{active_labels[2]} necesitan recuperarse."
    )


def _commercial_general_actions(
    *,
    summaries_by_metric: dict[str, dict[str, Any]],
    fallback: list[str],
) -> list[str]:
    labels = {
        "clientes_nuevos": "clientes nuevos",
        "reactivaciones": "reactivaciones",
        "domiciliados": "domiciliados",
    }

    targets: list[str] = []

    for metric_key in (
        "clientes_nuevos",
        "reactivaciones",
        "domiciliados",
    ):
        summary = summaries_by_metric.get(metric_key)
        if summary is None:
            continue

        if int(summary.get("remaining_days") or 0) <= 0:
            continue

        required = _operational_display_number(
            summary.get("required_daily_average")
        )

        if required is not None:
            targets.append(f"{required} {labels[metric_key]}")

    actions: list[str] = []

    if targets:
        if len(targets) == 1:
            target_text = targets[0]
        elif len(targets) == 2:
            target_text = f"{targets[0]} y {targets[1]}"
        else:
            target_text = (
                f"{targets[0]}, {targets[1]} y {targets[2]}"
            )

        actions.append(
            f"Objetivo diario: {target_text}."
        )

    actions.extend(fallback)

    return actions[:3]


def _build_recommendations(
    diagnosis: dict[str, Any],
    signals: Iterable[dict[str, Any]] = (),
    operational_summaries: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {
        "domiciliados": {
            "metric_key": "domiciliados",
            "title": "Recuperar domiciliaciones pendientes",
            "reason": (
                "Domiciliados opera debajo del ritmo esperado o muestra "
                "deterioro reciente."
            ),
            "actions": [
                "Revisar altas recientes que siguen sin domiciliación.",
                "Corregir tarjetas rechazadas o datos de pago incompletos.",
                "Dar seguimiento hoy a contratos pendientes.",
                "Dar seguimiento a pendientes del equipo comercial.",
            ],
            "evidence_keys": ["domiciliados"],
        },
        "retencion": {
            "metric_key": "bajas",
            "title": "Recuperar socios en riesgo",
            "reason": (
                "Las bajas están en zona crítica y los usuarios activos "
                "muestran deterioro."
            ),
            "actions": [
                "Revisar motivos de baja.",
                "Identificar socios recuperables.",
                "Priorizar contacto preventivo.",
                "Revisar fallas operativas recurrentes.",
            ],
            "evidence_keys": ["bajas", "usuarios"],
        },
        "bajas": {
            "metric_key": "bajas",
            "title": "Contener las bajas",
            "reason": (
                "Las bajas están en zona de atención o muestran "
                "aceleración reciente."
            ),
            "actions": [
                "Revisar motivos de baja recientes.",
                "Detectar si se repite el mismo motivo de baja.",
                "Contactar primero a los socios que todavía pueden recuperarse.",
                "Corregir incidencias que estén provocando bajas.",
            ],
            "evidence_keys": ["bajas"],
        },
        "clientes_nuevos": {
            "metric_key": "clientes_nuevos",
            "title": "Cerrar más clientes nuevos hoy",
            "reason": (
                "Clientes nuevos opera debajo del ritmo esperado o muestra "
                "deterioro reciente."
            ),
            "actions": [
                "Revisar prospectos que ya están cerca de cerrar.",
                "Contactar hoy a los prospectos más avanzados.",
                "Revisar si los prospectos pendientes están recibiendo seguimiento.",
            ],
            "evidence_keys": ["clientes_nuevos"],
        },
        "reactivaciones": {
            "metric_key": "reactivaciones",
            "title": "Buscar más reactivaciones hoy",
            "reason": (
                "Reactivaciones opera debajo del ritmo esperado o requiere "
                "seguimiento adicional."
            ),
            "actions": [
                "Contactar socios recientes que pueden reactivarse.",
                "Priorizar a quienes ya mostraron interés en regresar.",
                "Revisar si las reactivaciones pendientes están recibiendo seguimiento.",
                "Revisar motivos recurrentes de no reactivación.",
            ],
            "evidence_keys": ["reactivaciones"],
        },
        "ingreso": {
            "metric_key": "ingreso",
            "title": "Recuperar ingreso pendiente",
            "reason": (
                "La proyección histórica disponible ubica el cierre "
                "por debajo de la meta mensual."
            ),
            "actions": [
                "Revisar ventas pendientes de cobrar o completar.",
                "Revisar domiciliación de altas recientes.",
                "Confirmar que el ingreso de agregadoras esté reflejado.",
                "Revisar ventas complementarias pendientes.",
            ],
            "evidence_keys": ["ingreso"],
        },
        "comercial_general": {
            "metric_key": "clientes_nuevos",
            "title": "Acelerar cierres comerciales hoy",
            "reason": (
                "Más de un KPI comercial opera debajo del ritmo esperado."
            ),
            "actions": [
                "Revisar prospectos cercanos a cierre.",
                "Dar seguimiento hoy a cierres pendientes.",
                "Revisar contratos pendientes de domiciliación.",
                "Revisar dónde se están acumulando pendientes comerciales.",
            ],
            "evidence_keys": [
                "clientes_nuevos",
                "reactivaciones",
                "domiciliados",
            ],
        },
    }

    metric_template_keys = {
        "clientes_nuevos": "clientes_nuevos",
        "reactivaciones": "reactivaciones",
        "domiciliados": "domiciliados",
        "bajas": "bajas",
        "ingreso": "ingreso",
    }

    recommendations: list[dict[str, Any]] = []
    used_templates: set[str] = set()
    covered_metrics: set[str] = set()
    summaries_by_metric = _operational_summary_map(
        operational_summaries
    )

    def add_template(template_key: str | None) -> None:
        if not template_key or template_key in used_templates:
            return

        template = templates.get(template_key)
        if template is None:
            return

        recommendation = {
            "priority": len(recommendations) + 1,
            **template,
        }

        metric_key = str(template.get("metric_key") or "")
        summary = summaries_by_metric.get(metric_key)

        if template_key == "comercial_general":
            recommendation["reason"] = _commercial_general_reason(
                summaries_by_metric=summaries_by_metric,
                fallback=str(template["reason"]),
            )
            recommendation["actions"] = _commercial_general_actions(
                summaries_by_metric=summaries_by_metric,
                fallback=list(template["actions"]),
            )
        elif template_key in {
            "clientes_nuevos",
            "reactivaciones",
            "domiciliados",
        }:
            labels = {
                "clientes_nuevos": "Clientes nuevos",
                "reactivaciones": "Reactivaciones",
                "domiciliados": "Domiciliados",
            }
            recommendation["reason"] = _pace_recommendation_reason(
                label=labels[template_key],
                summary=summary,
                fallback=str(template["reason"]),
            )

            if (
                summary is not None
                and int(summary.get("remaining_days") or 0) > 0
            ):
                recent = _operational_display_number(
                    summary.get("recent_daily_average")
                )
                required = _operational_display_number(
                    summary.get("required_daily_average")
                )
                if recent is not None and required is not None:
                    recommendation["actions"] = list(
                        template["actions"]
                    )[:3]
        elif template_key in {"bajas", "retencion"}:
            bajas_summary = summaries_by_metric.get("bajas")

            recommendation["reason"] = _bajas_recommendation_reason(
                summary=bajas_summary,
                fallback=str(template["reason"]),
            )
            recommendation["actions"] = _bajas_recommendation_actions(
                summary=bajas_summary,
                fallback=list(template["actions"]),
            )
        elif template_key == "ingreso":
            recommendation["reason"] = _income_recommendation_reason(
                summary=summary,
                fallback=str(template["reason"]),
            )

        recommendations.append(recommendation)
        used_templates.add(template_key)
        covered_metrics.update(
            str(key)
            for key in template.get("evidence_keys", [])
        )

    primary_blocker = str(diagnosis.get("primary_blocker") or "")
    add_template(primary_blocker or None)

    severity_order = {
        "critical": 0,
        "warning": 1,
    }

    actionable_signals = [
        (index, signal)
        for index, signal in enumerate(signals)
        if str(signal.get("severity") or "") in severity_order
    ]
    actionable_signals.sort(
        key=lambda item: (
            severity_order[str(item[1].get("severity"))],
            item[0],
        )
    )

    for _, signal in actionable_signals:
        if len(recommendations) >= MAX_OPERATIONAL_RECOMMENDATIONS:
            break

        metric_key = str(signal.get("metric_key") or "")
        if not metric_key or metric_key in covered_metrics:
            continue

        add_template(metric_template_keys.get(metric_key))

    actionable_summaries = [
        (index, summary)
        for index, summary in enumerate(operational_summaries)
        if str(summary.get("severity") or "") in severity_order
    ]
    actionable_summaries.sort(
        key=lambda item: (
            severity_order[str(item[1].get("severity"))],
            item[0],
        )
    )

    for _, summary in actionable_summaries:
        if len(recommendations) >= MAX_OPERATIONAL_RECOMMENDATIONS:
            break

        metric_key = str(summary.get("metric_key") or "")
        if not metric_key or metric_key in covered_metrics:
            continue

        add_template(metric_template_keys.get(metric_key))

    return recommendations



def _business_rules() -> dict[str, Any]:
    return {
        "clientes_nuevos_pacing": "weekday_curve",
        "reactivaciones_pacing": "weekday_curve",
        "bajas_rule": "monthly_limit_consumption",
        "domiciliados_pacing": "weekday_curve",
        "domiciliados_formula": "clientes_nuevos_weekday_curve",
        "projection_method": "existing_stable_historical_pace",
        "operational_projection_method": OPERATIONAL_PROJECTION_METHOD,
        "operational_projection_window_calendar_days": (
            OPERATIONAL_PROJECTION_WINDOW_CALENDAR_DAYS
        ),
        "operational_projection_min_valid_deltas": (
            OPERATIONAL_PROJECTION_MIN_VALID_DELTAS
        ),
        "active_members_observed_source": "usuarios_activos_actual",
        "active_members_start_source": (
            "socios_activos_inicio_mes_not_propagated_to_track_daily_mart"
        ),
        "active_members_projection_method": (
            ACTIVE_MEMBERS_PROJECTION_METHOD
        ),
        "active_members_projection_formula": (
            "usuarios_activos_actual"
            "+clientes_nuevos_remaining_projected"
            "+reactivaciones_remaining_projected"
            "-bajas_remaining_projected"
        ),
        "income_signal_basis": "projected_close_vs_monthly_target_only",
        "trend_window_valid_cuts": TREND_WINDOW_VALID_CUTS,
        "trend_dead_band_pp": _decimal_string(TREND_DEAD_BAND_PP),
        "pace_severely_below_pct": _decimal_string(
            PACE_SEVERELY_BELOW_PCT
        ),
        "bajas_high_limit_usage_pct": _decimal_string(
            BAJAS_HIGH_LIMIT_USAGE_PCT
        ),
        "bajas_near_limit_usage_pct": _decimal_string(
            BAJAS_NEAR_LIMIT_USAGE_PCT
        ),
        "bajas_signal_precedence": [
            "bajas_limit_exceeded",
            "bajas_near_limit",
            "bajas_high_limit_usage",
        ],
        "income_linear_pacing_used": False,
        "recommendation_strategy": (
            "primary_blocker_plus_distinct_operational_risks"
        ),
        "recommendation_max_items": MAX_OPERATIONAL_RECOMMENDATIONS,
    }


def _resolve_authorized_branch(
    *,
    user: Any,
    sucursal_canon: str,
    track_date: date,
) -> ForecastCenterBranch:
    access = resolve_track_intelligence_access(user)

    # El universo se resuelve sin aplicar las restricciones del
    # Centro de Forecast. Inteligencia Operacional tiene su propio
    # contrato de autorización.
    universe_access = ForecastCenterAccess(
        type="global",
        is_global=True,
        authorized_branch_ids=(),
        authorized_branch_count=0,
        role=access.role,
    )

    universe = resolve_forecast_center_universe(
        access=universe_access,
        requested_track_date=track_date,
    )

    selected = select_forecast_center_scope(
        universe=universe,
        access=universe_access,
        scope="branch",
        scope_id=sucursal_canon,
        cohort="all",
    )

    if len(selected) != 1:
        raise TrackBranchOperationalDetailDataError(
            "La resolución de sucursal no produjo un resultado único."
        )

    branch = selected[0]

    if (
        not access.is_global
        and branch.sucursal_id != access.primary_branch_id
    ):
        raise TrackIntelligenceAuthorizationError(
            "Sucursal fuera del alcance autorizado."
        )

    return branch

def _calendar_dates(month_start: date, cutoff_date: date) -> list[date]:
    return [
        month_start + timedelta(days=offset)
        for offset in range((cutoff_date - month_start).days + 1)
    ]


def _month_end(month_start: date) -> date:
    return month_start.replace(
        day=monthrange(month_start.year, month_start.month)[1]
    )


def _build_chart_comparison_period_specs(
    track_date: date,
) -> dict[str, dict[str, Any]]:
    current_month = track_date.replace(day=1)
    previous_month = (current_month - timedelta(days=1)).replace(day=1)
    previous_year_same_month = current_month.replace(
        year=current_month.year - 1
    )
    period_bounds = {
        "current_month": (current_month, track_date),
        "previous_month": (
            previous_month,
            _month_end(previous_month),
        ),
        "previous_year_same_month": (
            previous_year_same_month,
            _month_end(previous_year_same_month),
        ),
    }
    result: dict[str, dict[str, Any]] = {}

    for period_key in CHART_COMPARISON_PERIOD_KEYS:
        month_start, date_to = period_bounds[period_key]
        days_in_month = monthrange(month_start.year, month_start.month)[1]
        comparison_day = min(track_date.day, days_in_month)
        result[period_key] = {
            "period_key": period_key,
            "target_month": month_start,
            "date_from": month_start,
            "date_to": date_to,
            "days_in_month": days_in_month,
            "comparison_day": comparison_day,
            "comparison_date": month_start.replace(day=comparison_day),
            "is_closed": date_to == _month_end(month_start),
            "calendar_dates": _calendar_dates(month_start, date_to),
        }

    return result


def _resolve_versions_for_dates(
    *,
    calendar_dates: Iterable[date],
) -> dict[date, Any]:
    resolved_versions: dict[date, Any] = {}

    for calendar_date in sorted(set(calendar_dates)):
        version = resolve_preferred_track_daily_version(
            track_date=calendar_date,
        )
        if version is not None:
            resolved_versions[calendar_date] = version

    return resolved_versions


def _load_branch_rows_for_versions(
    *,
    sucursal_canon: str,
    version_ids: Iterable[int],
) -> dict[int, TrackDailyMartORM]:
    normalized_ids = tuple(sorted({int(value) for value in version_ids}))
    if not normalized_ids:
        return {}
    rows = (
        db.session.query(TrackDailyMartORM)
        .filter(
            TrackDailyMartORM.track_daily_version_id.in_(normalized_ids),
            TrackDailyMartORM.sucursal_canon == sucursal_canon,
        )
        .all()
    )
    result: dict[int, TrackDailyMartORM] = {}
    for row in rows:
        version_id = int(row.track_daily_version_id)
        if version_id in result:
            raise TrackBranchOperationalDetailDataError(
                "La sucursal tiene más de una fila en una versión Track."
            )
        result[version_id] = row
    return result


def _build_history(
    *,
    calendar_dates: list[date],
    resolved_versions: dict[date, Any],
    rows_by_version: dict[int, TrackDailyMartORM],
    target_month: date,
) -> tuple[list[dict[str, Any]], list[str]]:
    history: list[dict[str, Any]] = []
    missing_dates: list[str] = []
    previous_point: dict[str, Any] | None = None

    for calendar_date in calendar_dates:
        version = resolved_versions.get(calendar_date)
        row = rows_by_version.get(int(version.id)) if version is not None else None
        if version is None or row is None:
            missing_dates.append(calendar_date.isoformat())
            continue
        if row.track_date != calendar_date:
            raise TrackBranchOperationalDetailDataError(
                "La fila del Mart no coincide con la fecha de su versión efectiva."
            )
        if row.target_month != target_month:
            raise TrackBranchOperationalDetailDataError(
                "La fila del Mart no coincide con el mes objetivo solicitado."
            )

        metrics = _build_metrics(row=row, cutoff_date=calendar_date)
        _add_daily_deltas(
            metrics=metrics,
            previous_metrics=(
                previous_point["metrics"] if previous_point is not None else None
            ),
        )
        previous_date = (
            date.fromisoformat(previous_point["track_date"])
            if previous_point is not None
            else None
        )
        days_since_previous = (
            (calendar_date - previous_date).days
            if previous_date is not None
            else None
        )
        point = {
            "track_date": calendar_date.isoformat(),
            "track_daily_version_id": int(version.id),
            "previous_track_date": (
                previous_date.isoformat() if previous_date is not None else None
            ),
            "days_since_previous": days_since_previous,
            "is_consecutive_previous_date": days_since_previous == 1,
            "metrics": metrics,
        }
        history.append(point)
        previous_point = point

    return history, missing_dates


def _build_chart_comparisons(
    *,
    period_specs: dict[str, dict[str, Any]],
    histories_by_period: dict[str, list[dict[str, Any]]],
    missing_dates_by_period: dict[str, list[str]],
) -> dict[str, Any]:
    periods: dict[str, dict[str, Any]] = {}

    for period_key in CHART_COMPARISON_PERIOD_KEYS:
        spec = period_specs[period_key]
        history = histories_by_period[period_key]
        missing_dates = missing_dates_by_period[period_key]
        periods[period_key] = {
            "period_key": period_key,
            "target_month": spec["target_month"].strftime("%Y-%m"),
            "date_from": spec["date_from"].isoformat(),
            "date_to": spec["date_to"].isoformat(),
            "days_in_month": spec["days_in_month"],
            "comparison_day": spec["comparison_day"],
            "comparison_date": spec["comparison_date"].isoformat(),
            "is_closed": spec["is_closed"],
            "history_rows": len(history),
            "expected_calendar_days": len(spec["calendar_dates"]),
            "missing_dates": missing_dates,
            "has_gaps": bool(missing_dates),
        }

    metrics: dict[str, dict[str, Any]] = {}
    for metric_key in CHART_COMPARISON_METRIC_KEYS:
        period_series: dict[str, dict[str, Any]] = {}

        for period_key in CHART_COMPARISON_PERIOD_KEYS:
            comparison_day = period_specs[period_key]["comparison_day"]
            points = [
                {
                    "track_date": point["track_date"],
                    "day_of_month": date.fromisoformat(
                        point["track_date"]
                    ).day,
                    "track_daily_version_id": point[
                        "track_daily_version_id"
                    ],
                    "actual_mtd": point["metrics"][metric_key].get(
                        "actual_mtd"
                    ),
                }
                for point in histories_by_period[period_key]
            ]
            same_day_point = next(
                (
                    point
                    for point in points
                    if point["day_of_month"] == comparison_day
                ),
                None,
            )
            period_series[period_key] = {
                "period_key": period_key,
                "points": points,
                "same_day_point": same_day_point,
            }

        metrics[metric_key] = {
            "metric_key": metric_key,
            "periods": period_series,
        }

    return {
        "periods": periods,
        "metrics": metrics,
    }


def _effective_generation_mode_for_version(
    *,
    version: Any | None,
    requested_generation_mode: str,
) -> str:
    if version is None:
        return requested_generation_mode

    if str(version.version_type) == "preview_operativo":
        return "manual_preview"

    return "official_closed_day"


def _preferred_version_fallback_used(
    *,
    version: Any | None,
) -> bool | None:
    if version is None:
        return None

    return bool(
        str(version.version_type) != PREFERRED_TRACK_VERSION_TYPES[0]
        or str(version.status) == "replaced"
    )


def get_track_branch_operational_detail(
    *,
    user: Any,
    sucursal_canon: str,
    track_date: date,
    generation_mode: str = "manual_preview",
    today: date | None = None,
) -> dict[str, Any]:
    normalized_branch = str(sucursal_canon or "").strip().upper()
    if not normalized_branch:
        raise ValueError("sucursal_canon es requerido.")

    local_today = today or get_track_local_today()
    if track_date > local_today:
        raise ValueError("track_date no puede ser una fecha futura.")

    branch = _resolve_authorized_branch(
        user=user,
        sucursal_canon=normalized_branch,
        track_date=track_date,
    )
    try:
        current_region = resolve_current_track_region_for_branch_id(
            sucursal_id=branch.sucursal_id,
        )
    except RuntimeError as exc:
        raise TrackBranchOperationalDetailDataError(
            "No se pudo resolver la región operacional actual "
            f"de la sucursal {branch.sucursal_canon!r}: {exc}"
        ) from exc

    target_month = track_date.replace(day=1)
    period_specs = _build_chart_comparison_period_specs(track_date)
    all_calendar_dates = [
        calendar_date
        for period_key in CHART_COMPARISON_PERIOD_KEYS
        for calendar_date in period_specs[period_key]["calendar_dates"]
    ]
    resolved_versions = _resolve_versions_for_dates(
        calendar_dates=all_calendar_dates,
    )

    rows_by_version = _load_branch_rows_for_versions(
        sucursal_canon=branch.sucursal_canon,
        version_ids=(version.id for version in resolved_versions.values()),
    )
    histories_by_period: dict[str, list[dict[str, Any]]] = {}
    missing_dates_by_period: dict[str, list[str]] = {}
    for period_key in CHART_COMPARISON_PERIOD_KEYS:
        spec = period_specs[period_key]
        period_history, period_missing_dates = _build_history(
            calendar_dates=spec["calendar_dates"],
            resolved_versions=resolved_versions,
            rows_by_version=rows_by_version,
            target_month=spec["target_month"],
        )
        histories_by_period[period_key] = period_history
        missing_dates_by_period[period_key] = period_missing_dates

    history = histories_by_period["current_month"]
    missing_dates = missing_dates_by_period["current_month"]
    dates = period_specs["current_month"]["calendar_dates"]
    chart_comparisons = _build_chart_comparisons(
        period_specs=period_specs,
        histories_by_period=histories_by_period,
        missing_dates_by_period=missing_dates_by_period,
    )
    current_version = resolved_versions.get(track_date)
    current_point = (
        history[-1]
        if history and history[-1]["track_date"] == track_date.isoformat()
        else None
    )
    current_metrics = (
        deepcopy(current_point["metrics"]) if current_point is not None else None
    )

    if current_metrics is not None:
        for metric_key in (*PACE_METRIC_KEYS, "bajas"):
            current_metrics[metric_key].update(
                _build_metric_trend(history, metric_key=metric_key)
            )
            benchmark_key = (
                "monthly_limit" if metric_key == "bajas" else "monthly_target"
            )
            current_metrics[metric_key]["projection"] = (
                _build_operational_projection(
                    history,
                    metric_key=metric_key,
                    cutoff_date=track_date,
                    actual_mtd=current_metrics[metric_key].get("actual_mtd"),
                    benchmark=current_metrics[metric_key].get(benchmark_key),
                )
            )
        current_metrics["socios_activos"]["projection"] = (
            _build_active_members_projection(
                metrics=current_metrics,
                cutoff_date=track_date,
            )
        )
        current_metrics["ingreso"]["projection"] = (
            build_branch_income_projection_summary(
                sucursal_canon=branch.sucursal_canon,
                target_month=target_month,
                cutoff_day=track_date.day,
                current_income_mtd=_decimal(
                    current_metrics["ingreso"].get("actual_mtd")
                ),
            )
        )

    signals = _build_operational_signals(current_metrics)
    operational_summaries = _build_operational_summaries(
        metrics=current_metrics,
        signals=signals,
    )
    diagnosis = _build_cross_metric_diagnosis(
        metrics=current_metrics,
        signals=signals,
    )
    projection = (
        current_metrics["ingreso"].get("projection")
        if current_metrics is not None
        else None
    )
    warnings: list[str] = []
    if current_version is None:
        warnings.append("No existe versión efectiva para el corte solicitado.")
    elif current_point is None:
        warnings.append("La versión efectiva no contiene la sucursal solicitada.")
    if missing_dates:
        warnings.append("El histórico mensual contiene fechas sin corte válido.")
    if projection and projection.get("status") != "available":
        warnings.append("La proyección de ingreso no está disponible.")

    return {
        "status": "ok",
        "identity": {
            "sucursal_canon": branch.sucursal_canon,
            "sucursal_label": branch.label,
            "region_key": (
                str(current_region.region_key)
                if current_region is not None
                else branch.region_key
            ),
            "region_label": (
                str(current_region.region_label)
                if current_region is not None
                else branch.region_label
            ),
        },
        "cutoff": {
            "track_date": track_date.isoformat(),
            "target_month": target_month.strftime("%Y-%m"),
            "generation_mode": _effective_generation_mode_for_version(
                version=current_version,
                requested_generation_mode=generation_mode,
            ),
            "track_daily_version_id": (
                int(current_version.id) if current_version is not None else None
            ),
            "version_type": (
                current_version.version_type if current_version is not None else None
            ),
            "days_in_month": monthrange(track_date.year, track_date.month)[1],
            "day_of_month": track_date.day,
            "resolved_by": "resolve_preferred_track_daily_version",
            "fallback_used": _preferred_version_fallback_used(
                version=current_version,
            ),
        },
        "current": {"metrics": current_metrics},
        "history": history,
        "chart_comparisons": chart_comparisons,
        "change_vs_previous": _build_change_vs_previous(
            history,
            current_track_date=track_date,
        ),
        "signals": signals,
        "operational_summaries": operational_summaries,
        "diagnosis": diagnosis,
        "recommendations": _build_recommendations(
            diagnosis=diagnosis,
            signals=signals,
            operational_summaries=operational_summaries,
        ),
        "quality": {
            "history_rows": len(history),
            "expected_calendar_days": len(dates),
            "missing_dates": missing_dates,
            "has_gaps": bool(missing_dates),
            "latest_version_available": current_point is not None,
            "projection_available": bool(
                projection and projection.get("status") == "available"
            ),
            "warnings": warnings,
        },
        "business_rules": _business_rules(),
    }
