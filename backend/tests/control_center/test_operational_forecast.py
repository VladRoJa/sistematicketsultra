from datetime import date
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
    "get_regional_operational_detail"
)
def test_global_scope_uses_all_branch_forecasts(get_regional):
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
    "get_regional_operational_detail"
)
def test_branch_scope_filters_before_aggregation(get_regional):
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
    assert result["branches"] == [
        {
            "sucursal_id": 2,
            "sucursal_canon": "B",
            "sucursal": "Sucursal B",
            "region_key": "R1",
            "region_label": "Región 1",
        }
    ]


@patch(
    "app.control_center.operational_forecast."
    "get_regional_operational_detail"
)
def test_missing_branch_contract_fails_closed(get_regional):
    response = _regional_response()
    response["regions"][0]["branches"][0].pop("operational_forecast")
    get_regional.return_value = response

    with pytest.raises(ControlOperationalForecastDataError):
        build_control_operational_forecast(
            user=SimpleNamespace(rol="ADMIN"),
            cutoff_date=date(2026, 9, 18),
            effective_scope=ControlScope(type="GLOBAL"),
        )
