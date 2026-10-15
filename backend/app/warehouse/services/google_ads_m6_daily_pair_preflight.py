"""Strict read-only preflight for one closed Google Ads M6 daily XLSX pair.

No mailbox authentication, uploads, approvals, facts or publication are done
here. The caller must independently establish trusted RAW provenance, approved
identities and the historical catalog before using this result.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

FIRST_DAILY_DATE = date(2026, 10, 13)
ZERO = Decimal("0")


class GoogleAdsM6DailyPairError(RuntimeError):
    pass


def preflight_daily_pair(
    *, business_date: date, today_local: date,
    campaign_report, group_report,
    historical_campaign_keys: set[str],
    historical_group_pairs: set[tuple[str, str]],
    approved_branch_by_pair: dict[tuple[str, str], str],
) -> dict:
    """Return a content-only preflight; NEVER an approval to publish."""
    if not isinstance(business_date, date) or not isinstance(today_local, date):
        raise GoogleAdsM6DailyPairError("INVALID_DATE")
    if business_date < FIRST_DAILY_DATE or business_date >= today_local:
        raise GoogleAdsM6DailyPairError("DAY_NOT_CLOSED_OR_OUT_OF_SCOPE")
    if campaign_report is None or group_report is None:
        return {
            "status": "WAITING_SOURCE",
            "business_date": business_date.isoformat(),
            "missing": [
                key for key, report in (
                    ("campaign", campaign_report), ("ad_group", group_report)
                ) if report is None
            ],
            "eligible_for_publication": False,
        }
    for report in (campaign_report, group_report):
        if (report.date_from != business_date or report.date_to != business_date
                or report.currency_code != "MXN"):
            raise GoogleAdsM6DailyPairError("REPORT_DATE_OR_CURRENCY_MISMATCH")
    # Frozen, reviewed M5/M6 historical catalog; never silently extend keys.
    if (len(historical_campaign_keys) != 27
            or len(historical_group_pairs) != 43
            or not {ck for ck, _ in historical_group_pairs}.issubset(
                historical_campaign_keys
            )):
        raise GoogleAdsM6DailyPairError("INVALID_HISTORICAL_CATALOG")
    if (len(approved_branch_by_pair) != 26
            or len(set(approved_branch_by_pair.values())) != 26
            or any(not name for name in approved_branch_by_pair.values())
            or not set(approved_branch_by_pair).issubset(
                historical_group_pairs
            )):
        raise GoogleAdsM6DailyPairError("INVALID_APPROVAL_CATALOG")

    campaigns = {}
    for row in campaign_report.rows:
        if row.report_date != business_date or row.currency_code != "MXN":
            raise GoogleAdsM6DailyPairError("INVALID_CAMPAIGN_ROW")
        if row.campaign_key in campaigns:
            raise GoogleAdsM6DailyPairError("DUPLICATE_CAMPAIGN")
        campaigns[row.campaign_key] = row
    if set(campaigns) != historical_campaign_keys:
        raise GoogleAdsM6DailyPairError("CAMPAIGN_IDENTITY_DRIFT")

    groups = {}
    group_totals = defaultdict(lambda: [ZERO, 0, 0])
    for row in group_report.rows:
        if row.report_date != business_date or row.currency_code != "MXN":
            raise GoogleAdsM6DailyPairError("INVALID_GROUP_ROW")
        key = (row.campaign_key, row.ad_group_key)
        if key in groups:
            raise GoogleAdsM6DailyPairError("DUPLICATE_GROUP")
        groups[key] = row
        subtotals = group_totals[row.campaign_key]
        subtotals[0] += Decimal(row.cost)
        subtotals[1] += int(row.clicks)
        subtotals[2] += int(row.impressions)
    if set(groups) != historical_group_pairs:
        raise GoogleAdsM6DailyPairError("GROUP_IDENTITY_DRIFT")
    for key, row in campaigns.items():
        if group_totals[key] != [
            Decimal(row.cost), int(row.clicks), int(row.impressions)
        ]:
            raise GoogleAdsM6DailyPairError(
                "CAMPAIGN_GROUP_RECONCILIATION_FAILED"
            )
    conversions_campaign = sum(
        (Decimal(row.conversions) for row in campaigns.values()), ZERO
    )
    conversions_group = sum(
        (Decimal(row.conversions) for row in groups.values()), ZERO
    )
    if abs(conversions_campaign - conversions_group) > Decimal("0.01"):
        raise GoogleAdsM6DailyPairError("CONVERSIONS_RECONCILIATION_FAILED")
    account = sum((Decimal(row.cost) for row in campaigns.values()), ZERO)
    attributed = sum(
        (Decimal(groups[key].cost) for key in approved_branch_by_pair), ZERO
    )
    if attributed > account:
        raise GoogleAdsM6DailyPairError("ASSIGNED_EXCEEDS_ACCOUNT")
    return {
        "status": "PREFLIGHT_OK",
        "business_date": business_date.isoformat(),
        "campaign_rows": len(campaigns),
        "group_rows": len(groups),
        "approved_branches": len(approved_branch_by_pair),
        "account_cost_mxn": str(account),
        "branch_cost_mxn": str(attributed),
        "unassigned_cost_mxn": str(account - attributed),
        "eligible_for_publication": False,
    }
