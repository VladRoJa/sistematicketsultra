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


def test_pre_crm_cutoffs_ignore_iventas_and_meta(monkeypatch):
    month_start = date(2026, 6, 1)
    month_end = date(2026, 6, 30)

    def fail_if_called(_month_start):
        raise AssertionError(
            "enero-junio no debe consultar fuentes CRM/Meta"
        )

    monkeypatch.setattr(
        service,
        "_iventas_cutoff_dates",
        fail_if_called,
    )
    monkeypatch.setattr(
        service,
        "_meta_cutoff_dates",
        fail_if_called,
    )
    monkeypatch.setattr(
        service,
        "_venta_total_cutoff_dates",
        lambda _month_start: {month_end},
    )
    monkeypatch.setattr(
        service,
        "_new_sales_cutoff_dates",
        lambda _month_start: {month_end},
    )
    monkeypatch.setattr(
        service,
        "_kpi_cutoff_dates",
        lambda _month_start: {month_end},
    )

    assert service.list_available_funnel_cutoffs(month_start) == (
        month_end,
    )


def test_crm_cutoffs_from_july_still_require_all_sources(monkeypatch):
    month_start = date(2026, 7, 1)
    month_end = date(2026, 7, 31)

    monkeypatch.setattr(
        service,
        "_iventas_cutoff_dates",
        lambda _month_start: set(),
    )
    monkeypatch.setattr(
        service,
        "_meta_cutoff_dates",
        lambda _month_start: {month_end},
    )
    monkeypatch.setattr(
        service,
        "_venta_total_cutoff_dates",
        lambda _month_start: {month_end},
    )
    monkeypatch.setattr(
        service,
        "_new_sales_cutoff_dates",
        lambda _month_start: {month_end},
    )
    monkeypatch.setattr(
        service,
        "_kpi_cutoff_dates",
        lambda _month_start: {month_end},
    )

    assert service.list_available_funnel_cutoffs(month_start) == ()


def test_pre_crm_payload_masks_only_crm_dependent_metrics():
    payload = {
        "summary": {
            "leads_iventas": 120,
            "sales_iventas": 30,
            "revenue_iventas": 9000.0,
            "visits_total": 80,
            "sales_total": 45,
            "sales_digital": 20,
            "total_visit_to_sale_rate": 0.5,
            "investment": 1500.0,
        },
        "branches": [
            {
                "sucursal_id": 1,
                "leads_iventas": 10,
                "sales_iventas": 3,
                "visits_total": 8,
                "sales_total": 4,
                "sales_digital": 2,
                "investment": 100.0,
            }
        ],
        "data_quality": {
            "match_mode": "exact_phone_same_branch_first_message_prior_30d",
            "commercial_classification_rule": "original",
            "survey_fallback_only_after_no_iventas_match": True,
        },
    }

    service._apply_crm_history_availability(
        payload=payload,
        crm_history_available=False,
    )

    assert payload["summary"]["leads_iventas"] is None
    assert payload["summary"]["sales_iventas"] is None
    assert payload["summary"]["revenue_iventas"] is None
    assert payload["summary"]["investment"] is None
    assert payload["branches"][0]["leads_iventas"] is None
    assert payload["branches"][0]["sales_iventas"] is None
    assert payload["branches"][0]["investment"] is None

    assert payload["summary"]["visits_total"] == 80
    assert payload["summary"]["sales_total"] == 45
    assert payload["summary"]["sales_digital"] == 20
    assert payload["summary"]["total_visit_to_sale_rate"] == 0.5
    assert payload["branches"][0]["visits_total"] == 8
    assert payload["branches"][0]["sales_total"] == 4
    assert payload["branches"][0]["sales_digital"] == 2

    quality = payload["data_quality"]
    assert quality["crm_history_available"] is False
    assert quality["crm_dependent_metrics_available"] is False
    assert quality["meta_available"] is False
    assert quality["crm_history_start_month"] == "2026-07"
    assert quality["match_mode"] is None


def test_crm_history_boundary_starts_in_july():
    assert service._crm_history_available(date(2026, 6, 1)) is False
    assert service._crm_history_available(date(2026, 7, 1)) is True


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
