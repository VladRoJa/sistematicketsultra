from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any

from app.control_center.access import ControlScope
from app.models.warehouse import TrackDailyMartORM
from app.track_alerts.services.track_regional_operational_service import (
    get_regional_operational_detail,
)
from app.warehouse.services.track_daily_query_version_service import (
    resolve_preferred_track_daily_version,
)
from app.warehouse.services.track_operational_forecast_service import (
    build_operational_forecast_scope_summary,
)


class ControlOperationalForecastDataError(RuntimeError):
    pass


HISTORICAL_METRIC_ATTRIBUTES = {
    "clientes_nuevos": "clientes_nuevos_real_mtd",
    "reactivaciones": "reactivaciones_real_mtd",
    "bajas": "bajas_reales_mtd",
    "tienda": "venta_tienda_real_mtd",
}


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _previous_month_same_day(cutoff_date: date) -> date:
    if cutoff_date.month == 1:
        year = cutoff_date.year - 1
        month = 12
    else:
        year = cutoff_date.year
        month = cutoff_date.month - 1

    day = min(cutoff_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _same_month_previous_year(cutoff_date: date) -> date:
    year = cutoff_date.year - 1
    day = min(
        cutoff_date.day,
        monthrange(year, cutoff_date.month)[1],
    )
    return date(year, cutoff_date.month, day)


def _month_end(value: date) -> date:
    return value.replace(
        day=monthrange(value.year, value.month)[1],
    )


def _historical_metric_value(
    row: TrackDailyMartORM,
    metric_key: str,
) -> Decimal | None:
    if metric_key == "ingreso":
        value = row.ingreso_real_total_mtd
        if value is None:
            value = row.ingreso_real_mtd
        return _decimal(value)

    attribute_name = HISTORICAL_METRIC_ATTRIBUTES[metric_key]
    return _decimal(getattr(row, attribute_name, None))


def _load_historical_metric_rows(
    *,
    track_date: date,
    sucursal_canons: list[str],
) -> dict[str, Any]:
    version = resolve_preferred_track_daily_version(
        track_date=track_date,
    )
    if version is None:
        return {
            "track_date": track_date.isoformat(),
            "version": None,
            "rows": {},
        }

    rows = (
        TrackDailyMartORM.query.filter(
            TrackDailyMartORM.track_daily_version_id == version.id,
            TrackDailyMartORM.sucursal_canon.in_(sucursal_canons),
        )
        .all()
    )

    rows_by_canon: dict[str, dict[str, Decimal | None]] = {}
    for row in rows:
        canon = str(row.sucursal_canon or "").strip()
        if not canon:
            continue
        if canon in rows_by_canon:
            raise ControlOperationalForecastDataError(
                "El histórico de Track contiene una sucursal duplicada "
                f"para la versión {version.id}: {canon}."
            )

        rows_by_canon[canon] = {
            metric_key: _historical_metric_value(row, metric_key)
            for metric_key in (
                "ingreso",
                "clientes_nuevos",
                "reactivaciones",
                "bajas",
                "tienda",
            )
        }

    return {
        "track_date": track_date.isoformat(),
        "version": {
            "id": int(version.id),
            "version_type": version.version_type,
            "status": version.status,
        },
        "rows": rows_by_canon,
    }


def _build_comparable_period(
    *,
    metric_key: str,
    branches: list[dict[str, Any]],
    historical_bundle: dict[str, Any],
    current_field: str,
) -> dict[str, Any]:
    historical_rows = historical_bundle.get("rows") or {}
    current_total = Decimal("0")
    historical_total = Decimal("0")
    comparable_branches = 0

    for branch in branches:
        canon = str(branch.get("sucursal_canon") or "").strip()
        current_metric = (branch.get("metrics") or {}).get(metric_key) or {}
        current_value = _decimal(current_metric.get(current_field))
        historical_value = (
            historical_rows.get(canon) or {}
        ).get(metric_key)

        if current_value is None or historical_value is None:
            continue

        current_total += current_value
        historical_total += historical_value
        comparable_branches += 1

    if comparable_branches == 0:
        return {
            "status": "unavailable",
            "comparison_date": historical_bundle.get("track_date"),
            "comparison_version": historical_bundle.get("version"),
            "current_comparable": None,
            "historical": None,
            "delta": None,
            "change_ratio": None,
            "comparable_branches": 0,
            "total_current_branches": len(branches),
        }

    delta = current_total - historical_total
    change_ratio = (
        delta / historical_total
        if historical_total != 0
        else None
    )

    return {
        "status": "available",
        "comparison_date": historical_bundle.get("track_date"),
        "comparison_version": historical_bundle.get("version"),
        "current_comparable": _decimal_string(current_total),
        "historical": _decimal_string(historical_total),
        "delta": _decimal_string(delta),
        "change_ratio": _decimal_string(change_ratio),
        "comparable_branches": comparable_branches,
        "total_current_branches": len(branches),
    }


def _build_historical_comparison(
    *,
    cutoff_date: date,
    branches: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_month_mtd = _previous_month_same_day(cutoff_date)
    previous_year_mtd = _same_month_previous_year(cutoff_date)
    period_dates = {
        "previous_month": {
            "mtd": previous_month_mtd,
            "close": _month_end(previous_month_mtd),
        },
        "previous_year": {
            "mtd": previous_year_mtd,
            "close": _month_end(previous_year_mtd),
        },
    }
    canons = [
        str(branch.get("sucursal_canon") or "").strip()
        for branch in branches
        if str(branch.get("sucursal_canon") or "").strip()
    ]

    bundles: dict[tuple[str, str], dict[str, Any]] = {}
    for period_key, dates in period_dates.items():
        for comparison_kind, comparison_date in dates.items():
            bundles[(period_key, comparison_kind)] = (
                _load_historical_metric_rows(
                    track_date=comparison_date,
                    sucursal_canons=canons,
                )
            )

    metrics: dict[str, Any] = {}
    for metric_key in (
        "ingreso",
        "clientes_nuevos",
        "reactivaciones",
        "bajas",
        "tienda",
    ):
        metrics[metric_key] = {}
        for period_key in ("previous_month", "previous_year"):
            metrics[metric_key][period_key] = {
                "mtd": _build_comparable_period(
                    metric_key=metric_key,
                    branches=branches,
                    historical_bundle=bundles[(period_key, "mtd")],
                    current_field="actual_mtd",
                ),
                "close": _build_comparable_period(
                    metric_key=metric_key,
                    branches=branches,
                    historical_bundle=bundles[(period_key, "close")],
                    current_field="projected_close",
                ),
            }

    return {
        "method": "common_branch_cohort_exact_day",
        "periods": {
            period_key: {
                "mtd_date": dates["mtd"].isoformat(),
                "close_date": dates["close"].isoformat(),
            }
            for period_key, dates in period_dates.items()
        },
        "metrics": metrics,
    }


def _normalize_branch_id(value: Any) -> int | None:
    try:
        branch_id = int(value)
    except (TypeError, ValueError):
        return None

    return branch_id if branch_id > 0 else None


def build_control_operational_forecast(
    *,
    user: Any,
    cutoff_date: date,
    effective_scope: ControlScope,
    generation_mode: str = "manual_preview",
) -> dict[str, Any]:
    regional = get_regional_operational_detail(
        user=user,
        track_date=cutoff_date,
        generation_mode=generation_mode,
    )

    allowed_branch_ids = (
        None
        if effective_scope.type == "GLOBAL"
        else set(effective_scope.branch_ids)
    )

    branch_forecasts: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    seen_branch_ids: set[int] = set()

    for region in regional.get("regions") or []:
        for branch in region.get("branches") or []:
            branch_id = _normalize_branch_id(branch.get("sucursal_id"))
            if branch_id is None:
                raise ControlOperationalForecastDataError(
                    "Seguimiento Regional devolvió una sucursal sin id válido."
                )

            if (
                allowed_branch_ids is not None
                and branch_id not in allowed_branch_ids
            ):
                continue

            if branch_id in seen_branch_ids:
                raise ControlOperationalForecastDataError(
                    "Seguimiento Regional devolvió una sucursal duplicada "
                    f"para Control: {branch_id}."
                )
            seen_branch_ids.add(branch_id)

            forecast = branch.get("operational_forecast")
            if not isinstance(forecast, dict):
                raise ControlOperationalForecastDataError(
                    "La sucursal no contiene el contrato de Forecast "
                    f"Operativo: {branch_id}."
                )

            branch_forecasts.append(forecast)
            branches.append(
                {
                    "sucursal_id": branch_id,
                    "sucursal_canon": branch.get("sucursal_canon"),
                    "sucursal": branch.get("sucursal_name"),
                    "region_key": region.get("region_key"),
                    "region_label": region.get("region_label"),
                    "metrics": forecast.get("metrics") or {},
                }
            )

    summary = build_operational_forecast_scope_summary(branch_forecasts)
    historical_comparison = _build_historical_comparison(
        cutoff_date=cutoff_date,
        branches=branches,
    )

    return {
        "status": "ok",
        "cutoff_date": cutoff_date.isoformat(),
        "generation_mode": generation_mode,
        "resolved_version": regional.get("resolved_version"),
        "summary": summary,
        "historical_comparison": historical_comparison,
        "branches": branches,
    }
