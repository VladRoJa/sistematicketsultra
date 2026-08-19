from datetime import date
from decimal import Decimal

import pytest

from app.track_alerts.services.track_regional_pacing_service import (
    CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    REACTIVACIONES_WEEKDAY_WEIGHTS,
    build_bajas_metric,
    build_clientes_nuevos_metric,
    build_normalized_monthly_curve,
    build_reactivaciones_metric,
    build_target_progress_metric,
    build_users_gap_metric,
    calculate_expected_progress_ratio,
)


@pytest.mark.parametrize(
    ("target_month", "expected_days", "expected_first_weekday"),
    [
        (date(2027, 2, 1), 28, 0),
        (date(2026, 6, 1), 30, 0),
        (date(2026, 8, 1), 31, 5),
    ],
)
@pytest.mark.parametrize(
    "weekday_weights",
    [
        CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
        REACTIVACIONES_WEEKDAY_WEIGHTS,
    ],
)
def test_monthly_curve_covers_calendar_and_sums_exactly_one(
    target_month,
    expected_days,
    expected_first_weekday,
    weekday_weights,
):
    curve = build_normalized_monthly_curve(
        target_month=target_month,
        weekday_weights=weekday_weights,
    )

    assert len(curve) == expected_days
    assert next(iter(curve)).weekday() == expected_first_weekday
    assert sum(curve.values()) == Decimal("1")


def test_expected_progress_is_cumulative_and_ends_at_one():
    middle = calculate_expected_progress_ratio(
        cutoff_date=date(2026, 8, 17),
        weekday_weights=CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    )
    month_end = calculate_expected_progress_ratio(
        cutoff_date=date(2026, 8, 31),
        weekday_weights=CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    )

    assert Decimal("0") < middle < Decimal("1")
    assert month_end == Decimal("1")


def test_clientes_nuevos_ahead_of_expected_pace():
    cutoff_date = date(2026, 8, 17)
    target = Decimal("180")
    expected_ratio = calculate_expected_progress_ratio(
        cutoff_date=cutoff_date,
        weekday_weights=CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    )
    actual = target * expected_ratio + Decimal("1")

    metric = build_clientes_nuevos_metric(
        actual_mtd=actual,
        monthly_target=target,
        cutoff_date=cutoff_date,
    )

    assert metric.status == "ADELANTADO"
    assert metric.gap_units is not None
    assert abs(metric.gap_units - Decimal("1")) < Decimal("1e-24")
    assert metric.gap_pct_points is not None
    assert metric.gap_pct_points > 0


def test_clientes_nuevos_exactly_on_expected_pace():
    cutoff_date = date(2026, 8, 17)
    target = Decimal("180")
    expected_ratio = calculate_expected_progress_ratio(
        cutoff_date=cutoff_date,
        weekday_weights=CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    )
    actual = target * expected_ratio

    metric = build_clientes_nuevos_metric(
        actual_mtd=actual,
        monthly_target=target,
        cutoff_date=cutoff_date,
    )

    assert metric.status == "EN_RITMO"
    assert metric.gap_units == Decimal("0")
    assert metric.gap_pct_points == Decimal("0")


def test_clientes_nuevos_below_expected_pace():
    cutoff_date = date(2026, 8, 17)
    target = Decimal("180")
    expected_ratio = calculate_expected_progress_ratio(
        cutoff_date=cutoff_date,
        weekday_weights=CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    )
    actual = target * expected_ratio - Decimal("1")

    metric = build_clientes_nuevos_metric(
        actual_mtd=actual,
        monthly_target=target,
        cutoff_date=cutoff_date,
    )

    assert metric.status == "DEBAJO_RITMO"
    assert metric.gap_units == Decimal("-1")
    assert metric.gap_pct_points is not None
    assert metric.gap_pct_points < 0


@pytest.mark.parametrize("monthly_target", [None, 0])
def test_clientes_nuevos_without_positive_target(monthly_target):
    metric = build_clientes_nuevos_metric(
        actual_mtd=10,
        monthly_target=monthly_target,
        cutoff_date=date(2026, 8, 17),
    )

    assert metric.status == "SIN_META"
    assert metric.actual_progress_pct is None
    assert metric.gap_pct_points is None


@pytest.mark.parametrize(
    ("offset", "expected_status"),
    [
        (Decimal("1"), "ADELANTADO"),
        (Decimal("0"), "EN_RITMO"),
        (Decimal("-1"), "DEBAJO_RITMO"),
    ],
)
def test_reactivaciones_compares_against_its_own_expected_pace(
    offset,
    expected_status,
):
    cutoff_date = date(2026, 8, 17)
    target = Decimal("120")
    expected_ratio = calculate_expected_progress_ratio(
        cutoff_date=cutoff_date,
        weekday_weights=REACTIVACIONES_WEEKDAY_WEIGHTS,
    )

    metric = build_reactivaciones_metric(
        actual_mtd=target * expected_ratio + offset,
        monthly_target=target,
        cutoff_date=cutoff_date,
    )

    assert metric.status == expected_status


@pytest.mark.parametrize("monthly_target", [None, 0])
def test_reactivaciones_without_positive_target(monthly_target):
    metric = build_reactivaciones_metric(
        actual_mtd=10,
        monthly_target=monthly_target,
        cutoff_date=date(2026, 8, 17),
    )

    assert metric.status == "SIN_META"


def test_reactivaciones_does_not_reuse_clientes_nuevos_curve():
    cutoff_date = date(2026, 8, 17)

    clientes_metric = build_clientes_nuevos_metric(
        actual_mtd=50,
        monthly_target=100,
        cutoff_date=cutoff_date,
    )
    reactivaciones_metric = build_reactivaciones_metric(
        actual_mtd=50,
        monthly_target=100,
        cutoff_date=cutoff_date,
    )

    assert (
        clientes_metric.expected_progress_pct
        != reactivaciones_metric.expected_progress_pct
    )


@pytest.mark.parametrize(
    ("actual", "expected_status", "expected_margin"),
    [
        (189, "EN_RITMO", Decimal("1")),
        (190, "EN_RITMO", Decimal("0")),
        (205, "LIMITE_EXCEDIDO", Decimal("-15")),
    ],
)
def test_bajas_uses_only_the_objective_monthly_limit(
    actual,
    expected_status,
    expected_margin,
):
    metric = build_bajas_metric(
        actual_mtd=actual,
        monthly_limit=190,
    )

    assert metric.status == expected_status
    assert metric.remaining_margin == expected_margin
    assert metric.limit_usage_pct == Decimal(actual) / Decimal("190") * 100


@pytest.mark.parametrize("monthly_limit", [None, 0])
def test_bajas_without_positive_limit(monthly_limit):
    metric = build_bajas_metric(
        actual_mtd=10,
        monthly_limit=monthly_limit,
    )

    assert metric.status == "SIN_META"
    assert metric.limit_usage_pct is None


@pytest.mark.parametrize(
    ("actual", "target", "expected_status", "expected_remaining"),
    [
        (80, 100, "DEBAJO_META", Decimal("20")),
        (100, 100, "EN_RITMO", Decimal("0")),
        (120, 100, "META_SUPERADA", Decimal("0")),
        (10, 0, "SIN_META", None),
        (10, None, "SIN_META", None),
    ],
)
def test_simple_target_metrics_do_not_apply_weekday_curve(
    actual,
    target,
    expected_status,
    expected_remaining,
):
    metric = build_target_progress_metric(
        metric_key="domiciliados",
        actual_mtd=actual,
        monthly_target=target,
    )

    assert metric.status == expected_status
    assert metric.remaining_to_target == expected_remaining
    assert not hasattr(metric, "expected_progress_pct")


def test_users_metric_is_only_current_minus_projected_close():
    metric = build_users_gap_metric(
        current_users=1020,
        projected_close_users=1000,
    )

    assert metric.status == "INFORMATIVO"
    assert metric.users_gap == Decimal("20")
    assert not hasattr(metric, "m2_sin_circulaciones")


def test_linear_pace_uses_calendar_day_progress():
    from datetime import date
    from decimal import Decimal

    from app.track_alerts.services.track_regional_pacing_service import (
        build_linear_pace_metric,
    )

    april = build_linear_pace_metric(
        metric_key="domiciliados",
        actual_mtd=Decimal("40"),
        monthly_target=Decimal("100"),
        cutoff_date=date(2026, 4, 15),
    )

    assert april.expected_progress_pct == Decimal("50.0")
    assert april.expected_mtd == Decimal("50.0")
    assert april.actual_progress_pct == Decimal("40.0")
    assert april.gap_units == Decimal("-10.0")
    assert april.status == "DEBAJO_RITMO"

    august = build_linear_pace_metric(
        metric_key="domiciliados",
        actual_mtd=Decimal("150"),
        monthly_target=Decimal("310"),
        cutoff_date=date(2026, 8, 18),
    )

    assert august.expected_mtd == Decimal("180")
    assert august.expected_progress_pct == (
        Decimal("18") / Decimal("31") * Decimal("100")
    )
    assert august.status == "DEBAJO_RITMO"

    month_end = build_linear_pace_metric(
        metric_key="domiciliados",
        actual_mtd=Decimal("100"),
        monthly_target=Decimal("100"),
        cutoff_date=date(2026, 2, 28),
    )

    assert month_end.expected_progress_pct == Decimal("100")
    assert month_end.expected_mtd == Decimal("100")
    assert month_end.status == "EN_RITMO"
