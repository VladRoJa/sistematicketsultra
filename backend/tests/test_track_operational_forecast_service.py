from datetime import date, timedelta
from decimal import Decimal

from app.track_alerts.services.track_operational_projection_service import (
    build_operational_projection,
)
from app.warehouse.services import track_operational_forecast_service as service


def _history(
    *,
    cutoff: date,
    clientes_delta: Decimal = Decimal("10"),
    reactivaciones_delta: Decimal = Decimal("8"),
    tienda_delta: Decimal = Decimal("100"),
):
    start = cutoff - timedelta(days=6)
    points = []

    for offset in range(7):
        point_date = start + timedelta(days=offset)
        previous = point_date - timedelta(days=1)
        points.append(
            {
                "track_date": point_date.isoformat(),
                "previous_track_date": previous.isoformat(),
                "days_since_previous": 1,
                "is_consecutive_previous_date": True,
                "metrics": {
                    "clientes_nuevos": {
                        "daily_delta": str(clientes_delta),
                    },
                    "reactivaciones": {
                        "daily_delta": str(reactivaciones_delta),
                    },
                    "tienda": {
                        "daily_delta": str(tienda_delta),
                    },
                },
            }
        )

    return points


def test_recent_projection_supports_tienda_through_compatibility_service():
    cutoff = date(2026, 9, 18)

    projection = build_operational_projection(
        _history(cutoff=cutoff),
        metric_key="tienda",
        cutoff_date=cutoff,
        actual_mtd=Decimal("948525"),
        benchmark=Decimal("1716952.65"),
    )

    assert projection["status"] == "available"
    assert projection["method"] == (
        "recent_valid_daily_average_7_calendar_days"
    )
    assert projection["recent_daily_average"] == "100"
    assert projection["remaining_days"] == 12
    assert projection["projected_close"] == "949725"


def test_bajas_historical_projection_uses_daily_median_share():
    projection = service.build_bajas_historical_projection(
        actual_mtd=Decimal("4857"),
        monthly_limit=Decimal("4684"),
        cutoff_day=18,
        progress_curve={
            "status": "available",
            "method": "chain_daily_median_share_of_month_close",
            "points": {
                18: {
                    "day": 18,
                    "samples_count": 42,
                    "p25": Decimal("0.64"),
                    "median": Decimal("0.674"),
                    "p75": Decimal("0.71"),
                }
            },
        },
    )

    expected = Decimal("4857") / Decimal("0.674")

    assert projection["status"] == "available"
    assert projection["method"] == (
        "chain_daily_median_share_of_month_close"
    )
    assert Decimal(projection["projected_close"]) == expected
    assert projection["historical_progress_pct"] == "67.400"
    assert projection["historical_samples_count"] == 42
    assert Decimal(projection["projected_excess_units"]) == (
        expected - Decimal("4684")
    )


def test_branch_contract_builds_five_official_forecast_metrics():
    cutoff = date(2026, 9, 18)
    history = _history(
        cutoff=cutoff,
        clientes_delta=Decimal("79"),
        reactivaciones_delta=Decimal("115"),
        tienda_delta=Decimal("52686"),
    )

    result = service.build_branch_operational_forecast(
        track_date=cutoff,
        history=history,
        income_actual_mtd=Decimal("13598946.41"),
        income_monthly_target=Decimal("26102874.57"),
        income_projection={
            "status": "available",
            "method": "existing_stable_historical_pace",
            "projected_close": "22990637.52",
        },
        clientes_nuevos_actual_mtd=Decimal("1421"),
        clientes_nuevos_monthly_target=Decimal("3552"),
        reactivaciones_actual_mtd=Decimal("2077"),
        reactivaciones_monthly_target=Decimal("3308"),
        bajas_actual_mtd=Decimal("4857"),
        bajas_monthly_limit=Decimal("4684"),
        bajas_progress_curve={
            "status": "available",
            "method": "chain_daily_median_share_of_month_close",
            "points": {
                18: {
                    "day": 18,
                    "samples_count": 42,
                    "p25": Decimal("0.64"),
                    "median": Decimal("0.674"),
                    "p75": Decimal("0.71"),
                }
            },
        },
        tienda_actual_mtd=Decimal("948525"),
        tienda_monthly_target=Decimal("1716952.65"),
    )

    assert set(result["metrics"]) == {
        "ingreso",
        "clientes_nuevos",
        "reactivaciones",
        "bajas",
        "tienda",
    }

    ingreso = result["metrics"]["ingreso"]
    assert ingreso["projected_close"] == "22990637.52"
    assert Decimal(ingreso["projected_gap"]) == (
        Decimal("22990637.52") - Decimal("26102874.57")
    )

    clientes = result["metrics"]["clientes_nuevos"]
    assert clientes["method"] == (
        "recent_valid_daily_average_7_calendar_days"
    )
    assert clientes["projected_close"] == "2369"
    assert clientes["projected_gap"] == "-1183"

    reactivaciones = result["metrics"]["reactivaciones"]
    assert reactivaciones["projected_close"] == "3457"
    assert reactivaciones["projected_gap"] == "149"

    bajas = result["metrics"]["bajas"]
    assert bajas["benchmark_kind"] == "limit"
    assert bajas["method"] == (
        "chain_daily_median_share_of_month_close"
    )
    assert Decimal(bajas["projected_excess"]) > 0

    tienda = result["metrics"]["tienda"]
    assert tienda["projected_close"] == "1580757"
    assert Decimal(tienda["projected_gap"]) == (
        Decimal("1580757") - Decimal("1716952.65")
    )


def test_scope_summary_sums_branch_forecasts_instead_of_reforecasting_total():
    branch_a = {
        "metrics": {
            metric_key: {
                "actual_mtd": "100",
                "projected_close": "150",
                "benchmark": "140",
                "status": "available",
                "method": "method_a",
            }
            for metric_key in service.OPERATIONAL_FORECAST_METRIC_KEYS
        }
    }
    branch_b = {
        "metrics": {
            metric_key: {
                "actual_mtd": "200",
                "projected_close": "260",
                "benchmark": "250",
                "status": "available",
                "method": "method_b",
            }
            for metric_key in service.OPERATIONAL_FORECAST_METRIC_KEYS
        }
    }

    result = service.build_operational_forecast_scope_summary(
        [branch_a, branch_b]
    )

    assert result["status"] == "available"
    assert result["total_branches"] == 2

    for metric_key, metric in result["metrics"].items():
        assert metric["actual_mtd"] == "300"
        assert metric["projected_close"] == "410"
        assert metric["benchmark"] == "390"
        assert metric["projected_gap"] == "20"
        assert metric["method"] == "sum_branch_operational_forecasts"
        assert metric["coverage"]["projected_available_branches"] == 2

    bajas = result["metrics"]["bajas"]
    assert bajas["projected_excess"] == "20"
    assert bajas["projected_remaining_margin"] == "0"


def test_scope_summary_does_not_publish_partial_projected_close():
    available = {
        "metrics": {
            metric_key: {
                "actual_mtd": "100",
                "projected_close": "150",
                "benchmark": "140",
                "status": "available",
                "method": "method_a",
            }
            for metric_key in service.OPERATIONAL_FORECAST_METRIC_KEYS
        }
    }
    unavailable = {
        "metrics": {
            metric_key: {
                "actual_mtd": "200",
                "projected_close": None,
                "benchmark": "250",
                "status": "insufficient_history",
                "method": "method_b",
            }
            for metric_key in service.OPERATIONAL_FORECAST_METRIC_KEYS
        }
    }

    result = service.build_operational_forecast_scope_summary(
        [available, unavailable]
    )

    assert result["status"] == "partial"

    for metric in result["metrics"].values():
        assert metric["actual_mtd"] == "300"
        assert metric["benchmark"] == "390"
        assert metric["projected_close"] is None
        assert metric["projected_gap"] is None
        assert metric["coverage"]["projected_available_branches"] == 1
        assert metric["coverage"]["unavailable_branches_count"] == 1
