from datetime import date

import pytest

from app.services.marketing_inputs_service import MarketingInputValidationError
from app.services import marketing_sales_funnel_cutoff_service as service


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
