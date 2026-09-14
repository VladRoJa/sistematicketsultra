from datetime import date, datetime

from app.services.marketing_recovery_business_service import (
    BUSINESS_RESULT_REACTIVATION,
    BUSINESS_RESULT_RENEWAL,
    classify_recovery_business_result,
    enrich_campaign_outcome_detail_with_business_results,
)


def test_same_calendar_month_is_renewal():
    assert classify_recovery_business_result(
        expiration_date=date(2026, 9, 5),
        recovered_at_local=datetime(2026, 9, 18, 10, 0),
    ) == BUSINESS_RESULT_RENEWAL


def test_previous_month_is_reactivation():
    assert classify_recovery_business_result(
        expiration_date=date(2026, 8, 31),
        recovered_at_local=datetime(2026, 9, 1, 8, 0),
    ) == BUSINESS_RESULT_REACTIVATION


def test_older_expiration_is_reactivation():
    assert classify_recovery_business_result(
        expiration_date=date(2026, 6, 15),
        recovered_at_local=datetime(2026, 9, 14, 8, 0),
    ) == BUSINESS_RESULT_REACTIVATION


def test_year_boundary_uses_recovery_month():
    assert classify_recovery_business_result(
        expiration_date=date(2026, 12, 31),
        recovered_at_local=datetime(2027, 1, 2, 9, 0),
    ) == BUSINESS_RESULT_REACTIVATION


def test_missing_or_inconsistent_dates_are_not_classified():
    assert classify_recovery_business_result(
        expiration_date=None,
        recovered_at_local=datetime(2026, 9, 14, 8, 0),
    ) is None
    assert classify_recovery_business_result(
        expiration_date=date(2026, 9, 20),
        recovered_at_local=datetime(2026, 9, 14, 8, 0),
    ) is None


def test_detail_enrichment_splits_recovered_members_without_changing_technical_status():
    result = {
        "summary": {
            "sent": 4,
            "reactivated": 3,
            "pending": 1,
            "review": 0,
            "window_closed": 0,
            "in_tracking": 1,
            "conversion_rate": 75.0,
        },
        "rows": [
            {
                "status": "REACTIVATED",
                "fecha_vencimiento": "2026-09-05",
                "reactivated_at_local": "2026-09-18T10:00:00",
            },
            {
                "status": "REACTIVATED",
                "fecha_vencimiento": "2026-08-31",
                "reactivated_at_local": "2026-09-18T10:00:00",
            },
            {
                "status": "REACTIVATED",
                "fecha_vencimiento": None,
                "reactivated_at_local": "2026-09-18T10:00:00",
            },
            {
                "status": "PENDING",
                "fecha_vencimiento": "2026-09-10",
                "reactivated_at_local": None,
            },
        ],
    }

    enriched = enrich_campaign_outcome_detail_with_business_results(result)

    assert enriched["summary"]["recovered"] == 3
    assert enriched["summary"]["renewals"] == 1
    assert enriched["summary"]["reactivations"] == 1
    assert enriched["summary"]["unclassified_recovered"] == 1
    assert [row["business_result"] for row in enriched["rows"]] == [
        "RENOVACION",
        "REACTIVACION",
        None,
        None,
    ]
