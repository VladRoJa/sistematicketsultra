"""M2 Google Ads investment: cutoff alignment and scope isolation."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import marketing_google_ads_funnel_service as service


def row(day, spend, *, clicks=10, impressions=200, conversions=1):
    return SimpleNamespace(
        report_date=date(2026, 10, day),
        cost=Decimal(str(spend)),
        clicks=clicks,
        impressions=impressions,
        conversions=Decimal(str(conversions)),
    )


class DailyQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args):
        return self

    def group_by(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.items


def configure(monkeypatch, rows):
    session = SimpleNamespace(query=lambda *args: DailyQuery(rows))
    monkeypatch.setattr(service, "db", SimpleNamespace(session=session))
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", "2739125201")


def read(month_start=date(2026, 10, 1), cutoff=date(2026, 10, 8),
         is_global=True):
    return service.read_google_ads_funnel_investment(
        month_start=month_start, cutoff_date=cutoff, is_global=is_global
    )


def test_complete_month_to_cutoff_can_be_combined(monkeypatch):
    configure(monkeypatch, [row(day, 100) for day in range(1, 9)])
    data = read()
    assert data["status"] == "complete"
    assert data["amount"] == 800.0
    assert data["covered_days"] == 8
    assert data["missing_days"] == 0
    assert data["complete_to_cutoff"] is True
    assert data["clicks"] == 80

    combined = service.build_funnel_investment_sources(
        meta_assigned=700.0, google_ads=data,
    )
    assert combined["combined"] == 1500.0
    assert combined["existing_cpl_cpt_cac_basis"] == "META_ASSIGNED_ONLY"


def test_partial_data_never_produces_combined_total(monkeypatch):
    configure(monkeypatch, [row(day, 100) for day in range(1, 9)])
    data = read(cutoff=date(2026, 10, 12))
    assert data["status"] == "partial"
    assert data["missing_days"] == 4
    assert data["amount"] == 800.0
    assert service.build_funnel_investment_sources(
        meta_assigned=700.0, google_ads=data,
    )["combined"] is None


def test_historical_month_with_missing_first_days_is_partial(monkeypatch):
    configure(monkeypatch, [SimpleNamespace(
        report_date=date(2026, 9, day),
        cost=Decimal("5.00"),
        clicks=1, impressions=10, conversions=Decimal("0"),
    ) for day in range(24, 31)])
    data = read(month_start=date(2026, 9, 1),
                cutoff=date(2026, 9, 30))
    assert data["status"] == "partial"
    assert data["data_from"] == "2026-09-24"
    assert data["missing_days"] == 23


def test_scoped_access_does_not_query_or_disclose_account_totals(monkeypatch):
    monkeypatch.setattr(
        service, "db", SimpleNamespace(
            session=SimpleNamespace(
                query=lambda *args: pytest.fail("Must not query global Google Ads")
            )
        ),
    )
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", "2739125201")
    data = read(is_global=False)
    assert data["status"] == "scope_unavailable"
    assert data["amount"] is None
    assert data["complete_to_cutoff"] is False


def test_no_data_is_not_zero(monkeypatch):
    configure(monkeypatch, [])
    data = read()
    assert data["status"] == "no_data"
    assert data["amount"] is None
    assert service.build_funnel_investment_sources(
        meta_assigned=300.0, google_ads=data,
    )["combined"] is None


def test_no_account_config_is_not_zero(monkeypatch):
    monkeypatch.delenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", raising=False)
    data = read()
    assert data["status"] == "not_configured"
    assert data["amount"] is None
