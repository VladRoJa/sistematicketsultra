from datetime import date

from app.services.marketing_iventas_period_service import (
    build_iventas_month_date_range,
    build_iventas_month_period_key,
)


def test_builds_canonical_iventas_month_period_key():
    assert (
        build_iventas_month_period_key(
            date(2026, 8, 1)
        )
        == "IVENTAS-2026-08"
    )


def test_same_month_always_uses_same_period_key():
    expected = "IVENTAS-2026-08"

    assert build_iventas_month_period_key(
        date(2026, 8, 1)
    ) == expected

    assert build_iventas_month_period_key(
        date(2026, 8, 13)
    ) == expected

    assert build_iventas_month_period_key(
        date(2026, 8, 31)
    ) == expected


def test_builds_current_month_mtd_date_range():
    date_from, date_to = build_iventas_month_date_range(
        month_date=date(2026, 8, 1),
        today=date(2026, 8, 13),
    )

    assert date_from == date(2026, 8, 1)
    assert date_to == date(2026, 8, 13)


def test_builds_closed_historical_month_full_date_range():
    date_from, date_to = build_iventas_month_date_range(
        month_date=date(2026, 7, 1),
        today=date(2026, 8, 13),
    )

    assert date_from == date(2026, 7, 1)
    assert date_to == date(2026, 7, 31)


def test_rejects_future_month_date_range():
    import pytest

    with pytest.raises(
        ValueError,
        match="mes futuro",
    ):
        build_iventas_month_date_range(
            month_date=date(2026, 9, 1),
            today=date(2026, 8, 13),
        )


def test_resolves_complete_current_month_period_contract():
    from app.services.marketing_iventas_period_service import (
        MarketingIventasMonthPeriod,
        resolve_iventas_month_period,
    )

    period = resolve_iventas_month_period(
        month_date=date(2026, 8, 13),
        today=date(2026, 8, 13),
    )

    assert isinstance(
        period,
        MarketingIventasMonthPeriod,
    )
    assert period.period_key == "IVENTAS-2026-08"
    assert period.date_from == date(2026, 8, 1)
    assert period.date_to == date(2026, 8, 13)
