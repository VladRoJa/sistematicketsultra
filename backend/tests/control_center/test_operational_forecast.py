from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.control_center.access import ControlScope
from app.control_center.operational_forecast import (
    ControlOperationalForecastDataError,
    build_control_operational_forecast,
)


def _forecast(actual: str, projected: str, benchmark: str):
    metrics = {}

    for metric_key in (
        "ingreso",
        "clientes_nuevos",
        "reactivaciones",
        "bajas",
        "tienda",
    ):
        metrics[metric_key] = {
            "metric_key": metric_key,
            "actual_mtd": actual,
            "projected_close": projected,
            "benchmark": benchmark,
            "benchmark_kind": (
                "limit" if metric_key == "bajas" else "target"
            ),
            "projected_gap": str(
                float(projected) - float(benchmark)
            ),
            "status": "available",
            "method": f"method_{metric_key}",
            "projection": {
                "status": "available",
                "method": f"method_{metric_key}",
                "projected_close": projected,
            },
        }

    return {
        "track_date": "2026-09-18",
        "metrics": metrics,
    }


def _regional_response():
    return {
        "resolved_version": {
            "id": 3917,
            "version_type": "preview_operativo",
            "status": "success",
        },
        "regions": [
            {
                "region_key": "R1",
                "region_label": "Región 1",
                "branches": [
                    {
                        "sucursal_id": 1,
                        "sucursal_canon": "A",
                        "sucursal_name": "Sucursal A",
                        "operational_forecast": _forecast(
                            "100", "150", "140"
                        ),
                    },
                    {
                        "sucursal_id": 2,
                        "sucursal_canon": "B",
                        "sucursal_name": "Sucursal B",
                        "operational_forecast": _forecast(
                            "200", "260", "250"
                        ),
                    },
                ],
            }
        ],
    }


@patch(
    "app.control_center.operational_forecast."
    "_load_historical_metric_rows",
    return_value={
        "track_date": "2026-08-18",
        "version": None,
        "rows": {},
    },
)
@patch(
    "app.control_center.operational_forecast."
    "get_regional_operational_detail"
)
def test_global_scope_uses_all_branch_forecasts(
    get_regional,
    _load_history,
):
    get_regional.return_value = _regional_response()

    result = build_control_operational_forecast(
        user=SimpleNamespace(rol="ADMIN"),
        cutoff_date=date(2026, 9, 18),
        effective_scope=ControlScope(type="GLOBAL"),
    )

    ingreso = result["summary"]["metrics"]["ingreso"]

    assert result["resolved_version"]["id"] == 3917
    assert result["summary"]["total_branches"] == 2
    assert ingreso["actual_mtd"] == "300"
    assert ingreso["projected_close"] == "410"
    assert ingreso["benchmark"] == "390"
    assert ingreso["projected_gap"] == "20"


@patch(
    "app.control_center.operational_forecast."
    "_load_historical_metric_rows",
    return_value={
        "track_date": "2026-08-18",
        "version": None,
        "rows": {},
    },
)
@patch(
    "app.control_center.operational_forecast."
    "get_regional_operational_detail"
)
def test_branch_scope_filters_before_aggregation(
    get_regional,
    _load_history,
):
    get_regional.return_value = _regional_response()

    result = build_control_operational_forecast(
        user=SimpleNamespace(rol="ADMIN"),
        cutoff_date=date(2026, 9, 18),
        effective_scope=ControlScope(
            type="BRANCH",
            branch_ids=(2,),
        ),
    )

    ingreso = result["summary"]["metrics"]["ingreso"]

    assert result["summary"]["total_branches"] == 1
    assert ingreso["actual_mtd"] == "200"
    assert ingreso["projected_close"] == "260"
    assert ingreso["benchmark"] == "250"
    assert len(result["branches"]) == 1
    branch = result["branches"][0]
    assert branch["sucursal_id"] == 2
    assert branch["sucursal_canon"] == "B"
    assert branch["sucursal"] == "Sucursal B"
    assert branch["region_key"] == "R1"
    assert branch["region_label"] == "Región 1"
    assert branch["metrics"]["ingreso"]["actual_mtd"] == "200"
    assert branch["metrics"]["ingreso"]["projected_close"] == "260"
    assert branch["metrics"]["ingreso"]["projected_gap"] == "10.0"


@patch(
    "app.control_center.operational_forecast."
    "_load_historical_metric_rows",
    return_value={
        "track_date": "2026-08-18",
        "version": None,
        "rows": {},
    },
)
@patch(
    "app.control_center.operational_forecast."
    "get_regional_operational_detail"
)
def test_missing_branch_contract_fails_closed(
    get_regional,
    _load_history,
):
    response = _regional_response()
    response["regions"][0]["branches"][0].pop("operational_forecast")
    get_regional.return_value = response

    with pytest.raises(ControlOperationalForecastDataError):
        build_control_operational_forecast(
            user=SimpleNamespace(rol="ADMIN"),
            cutoff_date=date(2026, 9, 18),
            effective_scope=ControlScope(type="GLOBAL"),
        )


@patch(
    "app.control_center.operational_forecast."
    "_load_historical_metric_rows"
)
@patch(
    "app.control_center.operational_forecast."
    "get_regional_operational_detail"
)
def test_historical_comparison_uses_common_branch_cohort(
    get_regional,
    load_history,
):
    get_regional.return_value = _regional_response()

    historical_by_date = {
        date(2026, 8, 18): {
            "A": Decimal("90"),
            "B": Decimal("180"),
        },
        date(2026, 8, 31): {
            "A": Decimal("145"),
            "B": Decimal("250"),
        },
        date(2025, 9, 18): {
            "A": Decimal("80"),
        },
        date(2025, 9, 30): {
            "A": Decimal("140"),
        },
    }

    def fake_history(*, track_date, sucursal_canons):
        values = historical_by_date[track_date]
        return {
            "track_date": track_date.isoformat(),
            "version": {
                "id": 1000 + track_date.day,
                "version_type": "cierre_canonico",
                "status": "success",
            },
            "rows": {
                canon: {
                    metric_key: value
                    for metric_key in (
                        "ingreso",
                        "clientes_nuevos",
                        "reactivaciones",
                        "bajas",
                        "tienda",
                    )
                }
                for canon, value in values.items()
                if canon in sucursal_canons
            },
        }

    load_history.side_effect = fake_history

    result = build_control_operational_forecast(
        user=SimpleNamespace(rol="ADMIN"),
        cutoff_date=date(2026, 9, 18),
        effective_scope=ControlScope(type="GLOBAL"),
    )

    ingreso = result["historical_comparison"]["metrics"]["ingreso"]

    previous_month_mtd = ingreso["previous_month"]["mtd"]
    assert previous_month_mtd["status"] == "available"
    assert previous_month_mtd["current_comparable"] == "300"
    assert previous_month_mtd["historical"] == "270"
    assert previous_month_mtd["delta"] == "30"
    assert previous_month_mtd["change_ratio"] == str(
        Decimal("30") / Decimal("270")
    )
    assert previous_month_mtd["comparable_branches"] == 2
    assert previous_month_mtd["total_current_branches"] == 2

    previous_month_close = ingreso["previous_month"]["close"]
    assert previous_month_close["current_comparable"] == "410"
    assert previous_month_close["historical"] == "395"
    assert previous_month_close["delta"] == "15"

    previous_year_mtd = ingreso["previous_year"]["mtd"]
    assert previous_year_mtd["current_comparable"] == "100"
    assert previous_year_mtd["historical"] == "80"
    assert previous_year_mtd["comparable_branches"] == 1
    assert previous_year_mtd["total_current_branches"] == 2

    previous_year_close = ingreso["previous_year"]["close"]
    assert previous_year_close["current_comparable"] == "150"
    assert previous_year_close["historical"] == "140"
    assert previous_year_close["comparable_branches"] == 1
