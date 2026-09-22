from datetime import date

import pytest

from app.services.marketing_inputs_service import MarketingInputValidationError
from app.services import marketing_sales_funnel_cutoff_service as service


def test_registered_only_mode_keeps_only_real_visits(monkeypatch):
    registered = [object()]
    sales = [object()]

    def fail_if_adjusted(**_kwargs):
        raise AssertionError("registered_only no debe crear visitas ajustadas")

    monkeypatch.setattr(
        service,
        "_merge_visits_with_direct_purchases",
        fail_if_adjusted,
    )

    result = service._resolve_visits_for_mode(
        registered_visits=registered,
        sales=sales,
        include_direct_purchases=False,
    )

    assert result == registered
    assert result is not registered


def test_cutoff_venta_total_rows_include_payment_method():
    keys = {
        column.key
        for column in service.VENTA_TOTAL_CUTOFF_ROW_COLUMNS
    }

    assert "forma_pago" in keys


def test_parse_cutoff_date_requires_same_month():
    month_start = date(2026, 9, 1)

    assert service.parse_cutoff_date(
        month_start=month_start,
        raw_value="2026-09-14",
    ) == date(2026, 9, 14)

    with pytest.raises(MarketingInputValidationError):
        service.parse_cutoff_date(
            month_start=month_start,
            raw_value="2026-08-31",
        )


def test_resolve_cutoff_defaults_to_latest_common(monkeypatch):
    available = (
        date(2026, 9, 14),
        date(2026, 9, 13),
        date(2026, 9, 12),
    )
    monkeypatch.setattr(
        service,
        "list_available_funnel_cutoffs",
        lambda _month_start: available,
    )

    selected, options = service.resolve_funnel_cutoff(
        month_start=date(2026, 9, 1),
        requested_cutoff=None,
    )

    assert selected == date(2026, 9, 14)
    assert options == available


def test_resolve_cutoff_accepts_historical_common_date(monkeypatch):
    available = (
        date(2026, 9, 14),
        date(2026, 9, 13),
    )
    monkeypatch.setattr(
        service,
        "list_available_funnel_cutoffs",
        lambda _month_start: available,
    )

    selected, _ = service.resolve_funnel_cutoff(
        month_start=date(2026, 9, 1),
        requested_cutoff=date(2026, 9, 13),
    )

    assert selected == date(2026, 9, 13)


def test_resolve_cutoff_rejects_incomplete_date(monkeypatch):
    monkeypatch.setattr(
        service,
        "list_available_funnel_cutoffs",
        lambda _month_start: (date(2026, 9, 14),),
    )

    with pytest.raises(MarketingInputValidationError):
        service.resolve_funnel_cutoff(
            month_start=date(2026, 9, 1),
            requested_cutoff=date(2026, 9, 15),
        )


def test_resolve_cutoff_can_fallback_to_latest_complete_at_or_before(monkeypatch):
    available = (
        date(2026, 9, 19),
        date(2026, 9, 17),
        date(2026, 9, 16),
    )
    monkeypatch.setattr(
        service,
        "list_available_funnel_cutoffs",
        lambda _month_start: available,
    )

    selected, options = service.resolve_funnel_cutoff(
        month_start=date(2026, 9, 1),
        requested_cutoff=date(2026, 9, 18),
        cutoff_policy=(
            service.FUNNEL_CUTOFF_POLICY_LATEST_AVAILABLE_AT_OR_BEFORE
        ),
    )

    assert selected == date(2026, 9, 17)
    assert options == available


def test_resolve_cutoff_fallback_never_uses_future_date(monkeypatch):
    monkeypatch.setattr(
        service,
        "list_available_funnel_cutoffs",
        lambda _month_start: (date(2026, 9, 19),),
    )

    with pytest.raises(MarketingInputValidationError):
        service.resolve_funnel_cutoff(
            month_start=date(2026, 9, 1),
            requested_cutoff=date(2026, 9, 18),
            cutoff_policy=(
                service.FUNNEL_CUTOFF_POLICY_LATEST_AVAILABLE_AT_OR_BEFORE
            ),
        )


def test_parse_cutoff_policy_rejects_unknown_value():
    with pytest.raises(MarketingInputValidationError):
        service.parse_cutoff_policy("magic")
