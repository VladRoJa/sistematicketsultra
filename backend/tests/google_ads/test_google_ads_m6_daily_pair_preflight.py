"""M6 daily pair preflight: synthetic data, zero writes."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as Row

import pytest
from app.warehouse.services.google_ads_m6_daily_pair_preflight import (
    GoogleAdsM6DailyPairError, preflight_daily_pair,
)

DAY = date(2026, 10, 13)
TODAY = date(2026, 10, 14)


def _pair():
    keys = ["name:" + format(i + 1, "064x") for i in range(27)]
    pairs = [(keys[min(i, 26)], "name:" + format(i + 100, "064x"))
             for i in range(43)]
    campaign = [
        Row(report_date=DAY, campaign_key=k, currency_code="MXN",
            cost=Decimal("5.00") if i == 0 else
                 Decimal("1.00") if i == 26 else Decimal("0.00"),
            clicks=3 if i == 0 else 0, impressions=30 if i == 0 else 0,
            conversions=Decimal("2") if i == 0 else Decimal("0"))
        for i, k in enumerate(keys)
    ]
    groups = [
        Row(report_date=DAY, campaign_key=k[0], ad_group_key=k[1],
            currency_code="MXN",
            cost=Decimal("5.00") if i == 0 else
                 Decimal("1.00") if i == 26 else Decimal("0.00"),
            clicks=3 if i == 0 else 0, impressions=30 if i == 0 else 0,
            conversions=Decimal("2") if i == 0 else Decimal("0"))
        for i, k in enumerate(pairs)
    ]
    return dict(
        business_date=DAY, today_local=TODAY,
        campaign_report=Row(date_from=DAY, date_to=DAY,
                            currency_code="MXN", rows=tuple(campaign)),
        group_report=Row(date_from=DAY, date_to=DAY,
                         currency_code="MXN", rows=tuple(groups)),
        historical_campaign_keys=set(keys),
        historical_group_pairs=set(pairs),
        approved_branch_by_pair={pairs[i]: "CLUB_" + str(i)
                                 for i in range(26)},
    )


def test_complete_content_preflight_does_not_authorize_publish():
    result = preflight_daily_pair(**_pair())
    assert result == {
        "status": "PREFLIGHT_OK", "business_date": "2026-10-13",
        "campaign_rows": 27, "group_rows": 43, "approved_branches": 26,
        "account_cost_mxn": "6.00", "branch_cost_mxn": "5.00",
        "unassigned_cost_mxn": "1.00", "eligible_for_publication": False,
    }


@pytest.mark.parametrize("missing", ["campaign_report", "group_report"])
def test_missing_source_never_means_zero(missing):
    kw = _pair()
    kw[missing] = None
    result = preflight_daily_pair(**kw)
    assert result["status"] == "WAITING_SOURCE"
    assert result["eligible_for_publication"] is False


@pytest.mark.parametrize(
    "key,value",
    [("business_date", date(2026, 10, 12)), ("today_local", DAY)],
)
def test_closed_day_and_m6_date_required(key, value):
    kw = _pair()
    kw[key] = value
    with pytest.raises(GoogleAdsM6DailyPairError, match="DAY_NOT_CLOSED"):
        preflight_daily_pair(**kw)


def test_mismatched_report_period():
    kw = _pair()
    kw["group_report"].date_to = date(2026, 10, 12)
    with pytest.raises(GoogleAdsM6DailyPairError, match="REPORT_DATE"):
        preflight_daily_pair(**kw)


def test_group_renamed_even_when_cost_matches():
    kw = _pair()
    kw["group_report"].rows[0].ad_group_key = "name:" + "f" * 64
    with pytest.raises(GoogleAdsM6DailyPairError, match="GROUP_IDENTITY_DRIFT"):
        preflight_daily_pair(**kw)


def test_missing_approved_branch():
    kw = _pair()
    kw["approved_branch_by_pair"].pop(next(iter(kw["approved_branch_by_pair"])))
    with pytest.raises(GoogleAdsM6DailyPairError, match="INVALID_APPROVAL_CATALOG"):
        preflight_daily_pair(**kw)


def test_extra_cent_rejected():
    kw = _pair()
    kw["group_report"].rows[0].cost = Decimal("5.01")
    with pytest.raises(GoogleAdsM6DailyPairError, match="RECONCILIATION_FAILED"):
        preflight_daily_pair(**kw)


def test_conversion_drift_rejected():
    kw = _pair()
    kw["group_report"].rows[0].conversions = Decimal("2.02")
    with pytest.raises(GoogleAdsM6DailyPairError, match="CONVERSIONS_RECONCILIATION"):
        preflight_daily_pair(**kw)


def test_duplicate_group_rejected():
    kw = _pair()
    kw["group_report"].rows += (kw["group_report"].rows[0],)
    with pytest.raises(GoogleAdsM6DailyPairError, match="DUPLICATE_GROUP"):
        preflight_daily_pair(**kw)


def test_changed_historical_catalog_rejected():
    kw = _pair()
    kw["historical_campaign_keys"].pop()
    with pytest.raises(GoogleAdsM6DailyPairError, match="INVALID_HISTORICAL"):
        preflight_daily_pair(**kw)
