from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from app.track_alerts.services import (
    track_branch_operational_detail_service as service,
)
from app.warehouse.services.track_forecast_center_service import (
    ForecastCenterBranch,
)


def _mart_row(*, track_date: date, **overrides):
    values = {
        "track_daily_version_id": track_date.day,
        "track_date": track_date,
        "target_month": track_date.replace(day=1),
        "m2_sin_circulaciones": Decimal("1000"),
        "clientes_nuevos_real_mtd": Decimal(track_date.day * 10),
        "meta_clientes_nuevos_mes": Decimal("310"),
        "reactivaciones_real_mtd": Decimal(track_date.day * 5),
        "meta_reactivaciones_mes": Decimal("155"),
        "bajas_reales_mtd": Decimal(track_date.day),
        "meta_bajas_mes": Decimal("32"),
        "nuevos_domiciliados_real_mtd": Decimal(track_date.day * 10),
        "meta_nuevos_domiciliados_mes": Decimal("310"),
        "ingreso_real_total_mtd": Decimal(track_date.day * 1000),
        "ingreso_real_mtd": Decimal(track_date.day * 900),
        "ingreso_real_base_mtd": Decimal(track_date.day * 800),
        "ingreso_real_agregadora_mtd": Decimal(track_date.day * 200),
        "meta_faycgo_mes": Decimal("31000"),
        "usuarios_inicio_mes": Decimal("1000"),
        "usuarios_activos_actual": Decimal(1000 - track_date.day),
        "proyeccion_usuarios_cierre_mes": Decimal("1010"),
        "venta_tienda_real_mtd": Decimal(track_date.day * 100),
        "meta_venta_tienda_mes": Decimal("3100"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _history_point(
    *,
    track_date: str,
    metric_key: str,
    comparison_value: str,
):
    field = "limit_usage_pct" if metric_key == "bajas" else "pace_pct"
    return {
        "track_date": track_date,
        "metrics": {metric_key: {field: comparison_value}},
    }


def _projection_history(
    *,
    metric_key: str,
    cutoff_date: date,
    daily_deltas: list[int],
) -> list[dict]:
    first_date = cutoff_date - timedelta(days=len(daily_deltas) - 1)
    return [
        {
            "track_date": (first_date + timedelta(days=index)).isoformat(),
            "previous_track_date": (
                (first_date + timedelta(days=index - 1)).isoformat()
                if index > 0
                else (first_date - timedelta(days=1)).isoformat()
            ),
            "days_since_previous": 1,
            "is_consecutive_previous_date": True,
            "metrics": {
                metric_key: {"daily_delta": str(daily_delta)},
            },
        }
        for index, daily_delta in enumerate(daily_deltas)
    ]


def _projection(
    *,
    metric_key: str,
    cutoff_date: date,
    daily_deltas: list[int],
    actual_mtd,
    benchmark,
):
    return service._build_operational_projection(
        _projection_history(
            metric_key=metric_key,
            cutoff_date=cutoff_date,
            daily_deltas=daily_deltas,
        ),
        metric_key=metric_key,
        cutoff_date=cutoff_date,
        actual_mtd=actual_mtd,
        benchmark=benchmark,
    )


def test_operational_projection_uses_seven_valid_daily_deltas():
    projection = _projection(
        metric_key="clientes_nuevos",
        cutoff_date=date(2026, 8, 10),
        daily_deltas=[1, 2, 3, 4, 5, 6, 7],
        actual_mtd=100,
        benchmark=200,
    )

    assert projection["status"] == "available"
    assert projection["valid_daily_deltas"] == 7
    assert projection["recent_daily_average"] == "4"
    assert projection["projected_close"] == "184"
    assert projection["projected_points"][0] == {
        "track_date": "2026-08-10",
        "projected_mtd": "100",
    }
    assert projection["projected_points"][-1] == {
        "track_date": "2026-08-31",
        "projected_mtd": "184",
    }


def test_operational_projection_uses_exactly_three_valid_daily_deltas():
    projection = _projection(
        metric_key="reactivaciones",
        cutoff_date=date(2026, 8, 10),
        daily_deltas=[1, 2, 3],
        actual_mtd=10,
        benchmark=100,
    )

    assert projection["status"] == "available"
    assert projection["valid_daily_deltas"] == 3
    assert projection["recent_daily_average"] == "2"
    assert projection["projected_close"] == "52"


def test_operational_projection_rejects_only_two_valid_daily_deltas():
    projection = _projection(
        metric_key="domiciliados",
        cutoff_date=date(2026, 8, 10),
        daily_deltas=[2, 4],
        actual_mtd=10,
        benchmark=100,
    )

    assert projection["status"] == "insufficient_history"
    assert projection["valid_daily_deltas"] == 2
    assert projection["recent_daily_average"] is None
    assert projection["projected_close"] is None
    assert projection["projected_points"] == []


def test_operational_projection_excludes_delta_after_calendar_gap():
    history = _projection_history(
        metric_key="clientes_nuevos",
        cutoff_date=date(2026, 8, 10),
        daily_deltas=[1, 2, 3, 40],
    )
    history[-1].update(
        {
            "previous_track_date": "2026-08-08",
            "days_since_previous": 2,
            "is_consecutive_previous_date": False,
        }
    )

    projection = service._build_operational_projection(
        history,
        metric_key="clientes_nuevos",
        cutoff_date=date(2026, 8, 10),
        actual_mtd=50,
        benchmark=100,
    )

    assert projection["status"] == "available"
    assert projection["valid_daily_deltas"] == 3
    assert projection["recent_daily_average"] == "2"


def test_operational_projection_preserves_negative_daily_deltas():
    projection = _projection(
        metric_key="clientes_nuevos",
        cutoff_date=date(2026, 8, 10),
        daily_deltas=[4, 2, -3],
        actual_mtd=20,
        benchmark=100,
    )

    assert projection["recent_daily_average"] == "1"
    assert projection["projected_close"] == "41"


def test_bajas_projection_preserves_negative_daily_delta():
    projection = _projection(
        metric_key="bajas",
        cutoff_date=date(2026, 8, 10),
        daily_deltas=[4, 2, -3],
        actual_mtd=50,
        benchmark=100,
    )

    assert projection["recent_daily_average"] == "1"
    assert projection["projected_close"] == "71"


def test_operational_projection_at_month_end_uses_observed_close():
    projection = _projection(
        metric_key="clientes_nuevos",
        cutoff_date=date(2026, 8, 31),
        daily_deltas=[],
        actual_mtd=88,
        benchmark=100,
    )

    assert projection["status"] == "available"
    assert projection["remaining_days"] == 0
    assert projection["projected_close"] == "88"
    assert projection["projected_points"] == []


def test_operational_projection_with_null_target_keeps_projected_close():
    projection = _projection(
        metric_key="reactivaciones",
        cutoff_date=date(2026, 8, 28),
        daily_deltas=[2, 2, 2],
        actual_mtd=80,
        benchmark=None,
    )

    assert projection["status"] == "available"
    assert projection["projected_close"] == "86"
    assert projection["projected_gap_units"] is None
    assert projection["projected_compliance_pct"] is None


def test_bajas_projection_with_null_limit_keeps_projected_close():
    projection = _projection(
        metric_key="bajas",
        cutoff_date=date(2026, 8, 28),
        daily_deltas=[2, 2, 2],
        actual_mtd=170,
        benchmark=None,
    )

    assert projection["status"] == "available"
    assert projection["projected_close"] == "176"
    assert projection["projected_excess_units"] is None
    assert projection["projected_remaining_margin"] is None
    assert projection["projected_limit_usage_pct"] is None


def test_operational_projection_reports_close_above_target():
    projection = _projection(
        metric_key="domiciliados",
        cutoff_date=date(2026, 8, 28),
        daily_deltas=[10, 10, 10],
        actual_mtd=90,
        benchmark=100,
    )

    assert projection["projected_close"] == "120"
    assert projection["projected_gap_units"] == "20"
    assert projection["projected_compliance_pct"] == "120.0"


def test_operational_projection_reports_close_below_target():
    projection = _projection(
        metric_key="clientes_nuevos",
        cutoff_date=date(2026, 8, 28),
        daily_deltas=[2, 2, 2],
        actual_mtd=80,
        benchmark=100,
    )

    assert projection["projected_close"] == "86"
    assert projection["projected_gap_units"] == "-14"
    assert projection["projected_compliance_pct"] == "86.00"


def test_bajas_projection_reports_close_above_limit():
    projection = _projection(
        metric_key="bajas",
        cutoff_date=date(2026, 8, 28),
        daily_deltas=[8, 8, 8],
        actual_mtd=190,
        benchmark=193,
    )

    assert projection["projected_close"] == "214"
    assert projection["projected_excess_units"] == "21"
    assert projection["projected_remaining_margin"] == "0"


def test_bajas_projection_reports_close_below_limit():
    projection = _projection(
        metric_key="bajas",
        cutoff_date=date(2026, 8, 28),
        daily_deltas=[2, 2, 2],
        actual_mtd=170,
        benchmark=193,
    )

    assert projection["projected_close"] == "176"
    assert projection["projected_excess_units"] == "0"
    assert projection["projected_remaining_margin"] == "17"


def test_domiciliados_uses_exact_calendar_linear_pacing():
    metric = service._build_pace_metric(
        metric_key="domiciliados",
        actual_mtd=150,
        monthly_target=310,
        cutoff_date=date(2026, 8, 18),
    )

    assert Decimal(metric["expected_mtd"]) == Decimal("180")
    assert Decimal(metric["expected_progress_pct"]) == (
        Decimal("18") / Decimal("31") * Decimal("100")
    )


@pytest.mark.parametrize(
    ("actual", "expected_status", "remaining", "excess"),
    [
        (79, "DENTRO_LIMITE", "21", "0"),
        (80, "CONSUMO_ALTO", "20", "0"),
        (90, "CERCA_LIMITE", "10", "0"),
        (100, "CERCA_LIMITE", "0", "0"),
        (101, "LIMITE_EXCEDIDO", "0", "1"),
    ],
)
def test_bajas_limit_states(actual, expected_status, remaining, excess):
    metric = service._build_bajas_operational_metric(
        actual_mtd=actual,
        monthly_limit=100,
    )

    assert metric["status"] == expected_status
    assert metric["remaining_before_limit"] == remaining
    assert metric["excess_units"] == excess


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("90", "89", "87.9"), "DETERIORATING"),
        (("90", "91", "92"), "IMPROVING"),
        (("90", "91", "91.99"), "STABLE"),
    ],
)
def test_pace_trend_uses_three_cuts_and_two_pp_dead_band(values, expected):
    history = [
        _history_point(
            track_date=f"2026-08-{index:02d}",
            metric_key="clientes_nuevos",
            comparison_value=value,
        )
        for index, value in enumerate(values, start=1)
    ]

    trend = service._build_metric_trend(
        history,
        metric_key="clientes_nuevos",
    )

    assert trend["trend"] == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("80", "81", "82"), "DETERIORATING"),
        (("82", "81", "80"), "IMPROVING"),
        (("80", "80.5", "81.99"), "STABLE"),
    ],
)
def test_bajas_trend_inverts_interpretation(values, expected):
    history = [
        _history_point(
            track_date=f"2026-08-{index:02d}",
            metric_key="bajas",
            comparison_value=value,
        )
        for index, value in enumerate(values, start=1)
    ]

    trend = service._build_metric_trend(history, metric_key="bajas")

    assert trend["trend"] == expected


def test_trend_is_insufficient_with_fewer_than_three_valid_cuts():
    history = [
        _history_point(
            track_date="2026-08-01",
            metric_key="domiciliados",
            comparison_value="80",
        ),
        _history_point(
            track_date="2026-08-02",
            metric_key="domiciliados",
            comparison_value="75",
        ),
    ]

    assert service._build_metric_trend(
        history,
        metric_key="domiciliados",
    )["trend"] == "INSUFFICIENT_DATA"


def test_history_gap_references_last_available_cut():
    dates = [date(2026, 8, day) for day in range(1, 4)]
    versions = {
        date(2026, 8, 1): SimpleNamespace(id=1),
        date(2026, 8, 3): SimpleNamespace(id=3),
    }
    rows = {
        1: _mart_row(track_date=date(2026, 8, 1)),
        3: _mart_row(track_date=date(2026, 8, 3)),
    }

    history, missing = service._build_history(
        calendar_dates=dates,
        resolved_versions=versions,
        rows_by_version=rows,
        target_month=date(2026, 8, 1),
    )

    assert missing == ["2026-08-02"]
    assert history[1]["previous_track_date"] == "2026-08-01"
    assert history[1]["days_since_previous"] == 2
    assert history[1]["is_consecutive_previous_date"] is False
    assert history[1]["metrics"]["clientes_nuevos"]["daily_delta"] == "20"


@pytest.mark.parametrize(
    ("usage", "expected_key"),
    [
        ("79.99", None),
        ("80", "bajas_high_limit_usage"),
        ("90", "bajas_near_limit"),
        ("101", "bajas_limit_exceeded"),
    ],
)
def test_bajas_signal_thresholds_have_precedence(usage, expected_key):
    signals = service._build_bajas_signals(
        {
            "limit_usage_pct": usage,
            "trend": "STABLE",
            "trend_net_change_pp": "0",
        }
    )
    limit_signals = [
        signal["signal_key"]
        for signal in signals
        if signal["signal_key"] != "bajas_recent_acceleration"
    ]

    assert limit_signals == ([] if expected_key is None else [expected_key])


def test_income_signal_uses_projection_and_never_linear_pacing():
    unavailable = service._build_income_signals(
        {
            "monthly_target": "100",
            "projection": {
                "status": "insufficient_history",
                "projected_close": None,
            },
        }
    )
    below = service._build_income_signals(
        {
            "monthly_target": "100",
            "projection": {
                "status": "available",
                "projected_close": "99",
                "method": "existing_stable_historical_pace",
            },
        }
    )

    assert [item["signal_key"] for item in unavailable] == [
        "projection_unavailable"
    ]
    assert [item["signal_key"] for item in below] == [
        "ingreso_projection_below_target"
    ]
    assert service._business_rules()["income_linear_pacing_used"] is False


def test_all_healthy_kpis_produce_healthy_diagnosis_without_critical_signal():
    metrics = {
        "clientes_nuevos": {"pace_pct": "101"},
        "reactivaciones": {"pace_pct": "102"},
        "domiciliados": {"pace_pct": "100"},
        "bajas": {"limit_usage_pct": "79"},
        "usuarios": {"change_from_start": "5"},
    }
    diagnosis = service._build_cross_metric_diagnosis(
        metrics=metrics,
        signals=[],
    )

    assert diagnosis["overall_status"] == "healthy"
    assert diagnosis["primary_blocker"] is None


def test_service_resolves_each_calendar_date_and_forecasts_only_current_cut():
    cutoff = date(2026, 8, 3)
    branch = ForecastCenterBranch(
        sucursal_canon="SALTILLO_VILLALTA",
        sucursal_id=1,
        label="Saltillo Villalta",
        display_order=1,
        operational_status="ACTIVA",
        cohort="legacy_21",
        region_key="MONTERREY_SALTILLO_SERRANIA",
        region_label="Monterrey / Saltillo / Serranía",
        region_assignment_status="available",
    )
    versions = {
        date(2026, 8, day): SimpleNamespace(
            id=day,
            version_type="cierre_canonico",
            status="success",
        )
        for day in range(1, 4)
    }
    rows = {
        day: _mart_row(track_date=date(2026, 8, day))
        for day in range(1, 4)
    }
    projection = {
        "status": "available",
        "method": "existing_stable_historical_pace",
        "projected_close": "32000",
        "quality_issue": None,
    }

    with patch.object(
            service,
            "_resolve_authorized_branch",
            return_value=branch,
        ), patch.object(
            service,
            "resolve_current_track_region_for_branch_id",
            return_value=SimpleNamespace(
                region_key=branch.region_key,
                region_label=branch.region_label,
            ),
        ), patch.object(
            service,
            "resolve_effective_track_daily_version",
        side_effect=lambda track_date, **_: versions[track_date],
    ) as resolve_version, patch.object(
        service,
        "_load_branch_rows_for_versions",
        return_value=rows,
    ), patch.object(
        service,
        "build_branch_income_projection_summary",
        return_value=projection,
    ) as build_projection:
        result = service.get_track_branch_operational_detail(
            user=SimpleNamespace(rol="ADMIN"),
            sucursal_canon="saltillo_villalta",
            track_date=cutoff,
            generation_mode="manual_preview",
            today=cutoff,
        )

    assert resolve_version.call_args_list == [
        call(
            track_date=date(2026, 8, day),
            generation_mode="manual_preview",
            today=cutoff,
        )
        for day in range(1, 4)
    ]
    build_projection.assert_called_once()
    assert result["cutoff"]["track_daily_version_id"] == 3
    assert result["identity"]["sucursal_label"] == "Saltillo Villalta"
    assert result["quality"]["history_rows"] == 3
    assert result["current"]["metrics"]["ingreso"]["projection"] == projection
    for metric_key in service.OPERATIONAL_PROJECTION_METRIC_KEYS:
        assert (
            result["current"]["metrics"][metric_key]["projection"]["status"]
            == "insufficient_history"
        )
    assert result["business_rules"]["trend_dead_band_pp"] == "2"
    assert result["business_rules"]["operational_projection_method"] == (
        "recent_valid_daily_average_7_calendar_days"
    )
    assert (
        result["business_rules"][
            "operational_projection_window_calendar_days"
        ]
        == 7
    )
    assert (
        result["business_rules"][
            "operational_projection_min_valid_deltas"
        ]
        == 3
    )


def test_current_region_inconsistency_becomes_data_error():
    cutoff = date(2026, 8, 3)
    branch = ForecastCenterBranch(
        sucursal_canon="SALTILLO_VILLALTA",
        sucursal_id=1,
        label="Saltillo Villalta",
        display_order=1,
        operational_status="ACTIVA",
        cohort="legacy_21",
        region_key="MONTERREY_SALTILLO_SERRANIA",
        region_label="Monterrey / Saltillo / Serranía",
        region_assignment_status="available",
    )

    with patch.object(
        service,
        "_resolve_authorized_branch",
        return_value=branch,
    ), patch.object(
        service,
        "resolve_current_track_region_for_branch_id",
        side_effect=RuntimeError(
            "La sucursal 1 tiene más de una región current."
        ),
    ), patch.object(
        service,
        "resolve_effective_track_daily_version",
    ) as resolve_version:
        with pytest.raises(
            service.TrackBranchOperationalDetailDataError,
            match="No se pudo resolver la región operacional actual",
        ):
            service.get_track_branch_operational_detail(
                user=SimpleNamespace(rol="ADMIN"),
                sucursal_canon="SALTILLO_VILLALTA",
                track_date=cutoff,
                today=cutoff,
            )

    resolve_version.assert_not_called()


def test_future_track_date_is_rejected_before_authorization():
    with patch.object(service, "_resolve_authorized_branch") as authorize:
        with pytest.raises(ValueError, match="fecha futura"):
            service.get_track_branch_operational_detail(
                user=SimpleNamespace(rol="ADMIN"),
                sucursal_canon="SALTILLO_VILLALTA",
                track_date=date(2026, 8, 20),
                today=date(2026, 8, 19),
            )

    authorize.assert_not_called()
