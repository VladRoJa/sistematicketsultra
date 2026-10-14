"""M6 approved Google Ads branch attribution for 09..12 October only.

M5 remains immutable and keeps its own reader. Future-day provenance is a
separate milestone gate: never infer a daily upload or silently extend this
fixed RAW pair (21604/21605). Restricted requests never query global spend,
foreign branch metrics or unassigned groups.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_

from app.extensions import db
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.models.google_ads_m6_continuity import (
    GoogleAdsBranchApprovalVersionORM,
    GoogleAdsBranchApprovedIdentityORM,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchCatalogORM
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.warehouse.services.google_ads_m5_identity_seed_service import _load as _load_m5
from app.warehouse.services.google_ads_m6_continuity_approval_service import (
    ACCOUNT_TOTAL,
    CAMPAIGN_UPLOAD_ID,
    CUSTOMER_ID,
    END,
    GROUP_UPLOAD_ID,
    M5_REFERENCE,
    M6_REFERENCE,
    START,
)

ZERO = Decimal("0")
PER_DAY_GROUPS = 43
PER_DAY_CAMPAIGNS = 27


def _empty(status: str, month_start: date, cutoff_date: date) -> dict:
    expected = (cutoff_date - month_start).days + 1
    return {
        "status": status, "currency": "MXN",
        "allocation_basis": "APPROVED_PROVISIONAL_XLSX",
        "requested_from": month_start.isoformat(),
        "requested_to": cutoff_date.isoformat(),
        "historical_from": START.isoformat(),
        "historical_to": END.isoformat(),
        "complete_to_cutoff": False,
        "covered_days": 0,
        "expected_days": expected,
        "missing_days": expected,
        "rows": [],
        "scope_attributed_cost": None,
    }


def _version():
    """Approval metadata is not spend; do not load foreign-branch identities."""
    return (
        db.session.query(GoogleAdsBranchApprovalVersionORM)
        .filter(GoogleAdsBranchApprovalVersionORM.customer_id == CUSTOMER_ID)
        .all()
    )


def _mapping_rows(version_id: int, branch_ids: tuple[int, ...]):
    mapping = GoogleAdsBranchApprovedIdentityORM
    catalog = TrackBranchCatalogORM
    return (
        db.session.query(mapping, catalog, Sucursal)
        .join(catalog, catalog.sucursal_canon == mapping.sucursal_canon)
        .join(Sucursal, Sucursal.sucursal_id == catalog.sucursal_id)
        .filter(
            mapping.approval_version_id == version_id,
            catalog.sucursal_id.in_(branch_ids),
        )
        .all()
    )


def _fact_rows(version_id: int, branch_ids: tuple[int, ...], start: date, end: date):
    mapping = GoogleAdsBranchApprovedIdentityORM
    catalog = TrackBranchCatalogORM
    fact = GoogleAdsAdGroupDailyMetricORM
    return (
        db.session.query(fact, mapping, catalog)
        .join(mapping, and_(
            fact.campaign_key == mapping.campaign_key,
            fact.ad_group_key == mapping.ad_group_key,
            mapping.approval_version_id == version_id,
        ))
        .join(catalog, catalog.sucursal_canon == mapping.sucursal_canon)
        .filter(
            catalog.sucursal_id.in_(branch_ids),
            fact.customer_id == CUSTOMER_ID,
            fact.source_upload_id == GROUP_UPLOAD_ID,
            fact.report_date.between(start, end),
        )
        .all()
    )


def _global_campaigns(start: date, end: date):
    return (
        db.session.query(GoogleAdsDailyMetricORM)
        .filter(
            GoogleAdsDailyMetricORM.customer_id == CUSTOMER_ID,
            GoogleAdsDailyMetricORM.report_date.between(start, end),
        )
        .all()
    )


def _global_groups(start: date, end: date):
    return (
        db.session.query(GoogleAdsAdGroupDailyMetricORM)
        .filter(
            GoogleAdsAdGroupDailyMetricORM.customer_id == CUSTOMER_ID,
            GoogleAdsAdGroupDailyMetricORM.report_date.between(start, end),
        )
        .all()
    )


def _valid_version(version) -> bool:
    return (
        version.customer_id == CUSTOMER_ID
        and version.approval_reference == M6_REFERENCE
        and version.source_approval_reference == M5_REFERENCE
        and version.valid_from == START
        and version.valid_to is None
        and version.source_campaign_upload_id == CAMPAIGN_UPLOAD_ID
        and version.source_ad_group_upload_id == GROUP_UPLOAD_ID
        and version.approved_by_user_id is not None
        and version.approved_on >= date(2026, 10, 13)
    )


def _valid_fact(fact, mapping, day_range: set[date]) -> bool:
    return (
        fact.customer_id == CUSTOMER_ID
        and fact.source_kind == "WAREHOUSE_XLSX"
        and fact.source_upload_id == GROUP_UPLOAD_ID
        and fact.currency_code == "MXN"
        and fact.campaign_id is None
        and fact.ad_group_id is None
        and fact.report_date in day_range
        and fact.campaign_key == mapping.campaign_key
        and fact.ad_group_key == mapping.ad_group_key
    )


def _valid_global_reconciliation(start: date, end: date, assigned_total: Decimal):
    """Only global users may scan the account ledger or excluded groups."""
    campaigns = _global_campaigns(start, end)
    groups = _global_groups(start, end)
    dates = {start + timedelta(days=i) for i in range((end - start).days + 1)}
    campaign_by_day = defaultdict(list)
    group_by_day = defaultdict(list)
    for row in campaigns:
        if (
            row.report_date not in dates
            or row.customer_id != CUSTOMER_ID
            or row.source_upload_id != CAMPAIGN_UPLOAD_ID
            or row.source_kind != "WAREHOUSE_XLSX"
            or row.currency_code != "MXN"
            or row.campaign_id is not None
        ):
            return None
        campaign_by_day[row.report_date].append(row)
    for row in groups:
        if (
            row.report_date not in dates
            or row.customer_id != CUSTOMER_ID
            or row.source_upload_id != GROUP_UPLOAD_ID
            or row.source_kind != "WAREHOUSE_XLSX"
            or row.currency_code != "MXN"
            or row.campaign_id is not None
            or row.ad_group_id is not None
        ):
            return None
        group_by_day[row.report_date].append(row)
    account_total = ZERO
    group_total = ZERO
    for day in dates:
        campaign_rows = campaign_by_day.get(day, [])
        group_rows = group_by_day.get(day, [])
        if len(campaign_rows) != PER_DAY_CAMPAIGNS or len(group_rows) != PER_DAY_GROUPS:
            return None
        if len({r.campaign_key for r in campaign_rows}) != PER_DAY_CAMPAIGNS:
            return None
        if len({(r.campaign_key, r.ad_group_key) for r in group_rows}) != PER_DAY_GROUPS:
            return None
        campaign_cost = sum((Decimal(r.cost) for r in campaign_rows), ZERO)
        group_cost = sum((Decimal(r.cost) for r in group_rows), ZERO)
        if (
            campaign_cost != group_cost
            or sum(int(r.clicks) for r in campaign_rows) !=
               sum(int(r.clicks) for r in group_rows)
            or sum(int(r.impressions) for r in campaign_rows) !=
               sum(int(r.impressions) for r in group_rows)
        ):
            return None
        account_total += campaign_cost
        group_total += group_cost
    if account_total != group_total or account_total < assigned_total:
        return None
    if start == START and end == END and account_total != ACCOUNT_TOTAL:
        return None
    return account_total, account_total - assigned_total


def read_google_ads_m6_branch_attribution(
    *, month_start: date, cutoff_date: date, access: MarketingAccess,
) -> dict:
    if cutoff_date < month_start or month_start.day != 1:
        raise ValueError("Rango M6 inválido: mes/corte.")
    result = _empty("unavailable", month_start, cutoff_date)
    start = max(month_start, START)
    end = min(cutoff_date, END)
    if start > end:
        return result
    _, allowed_branch_ids, _ = load_visible_marketing_branches(access)
    if not allowed_branch_ids:
        result["status"] = "scope_unavailable"
        return result
    version_rows = _version()
    if not version_rows:
        result["status"] = "pending_mapping"
        return result
    if len(version_rows) != 1 or not _valid_version(version_rows[0]):
        result["status"] = "requires_review"
        return result
    version = version_rows[0]
    try:
        manifest = _load_m5()
    except (RuntimeError, ValueError, OSError, KeyError):
        result["status"] = "requires_review"
        return result
    approved = {
        (row[2], row[3]): (row[4], int(row[5]))
        for row in manifest["rows"]
    }
    if (
        manifest.get("id") != M5_REFERENCE
        or manifest.get("customer_id") != CUSTOMER_ID
        or len(approved) != 26
    ):
        result["status"] = "requires_review"
        return result

    mappings = _mapping_rows(version.id, allowed_branch_ids)
    scoped = {}
    for mapping, catalog, branch in mappings:
        branch_id = int(catalog.sucursal_id)
        if (
            mapping.approval_version_id != version.id
            or approved.get((mapping.campaign_key, mapping.ad_group_key))
            != (mapping.sucursal_canon, branch_id)
            or mapping.sucursal_canon != catalog.sucursal_canon
            or catalog.is_track_active is not True
            or branch.sucursal_id != branch_id
            or branch.operational_status != "ACTIVA"
            or branch_id in scoped
        ):
            result["status"] = "requires_review"
            return result
        scoped[branch_id] = mapping
    if not scoped or set(scoped) != set(allowed_branch_ids):
        result["status"] = "pending_mapping"
        return result
    if access.is_global and len(scoped) != 26:
        result["status"] = "requires_review"
        return result

    facts = _fact_rows(version.id, tuple(sorted(scoped)), start, end)
    dates = {start + timedelta(days=i) for i in range((end - start).days + 1)}
    by_branch = defaultdict(list)
    seen = set()
    for fact, mapping, catalog in facts:
        branch_id = int(catalog.sucursal_id)
        key = (branch_id, fact.report_date)
        if (
            branch_id not in scoped
            or mapping.id != scoped[branch_id].id
            or mapping.sucursal_canon != catalog.sucursal_canon
            or not _valid_fact(fact, mapping, dates)
            or key in seen
        ):
            result["status"] = "requires_review"
            return result
        seen.add(key)
        by_branch[branch_id].append(fact)
    if any(
        {fact.report_date for fact in by_branch.get(branch_id, ())} != dates
        for branch_id in scoped
    ):
        result["status"] = "requires_review"
        return result

    attributed = ZERO
    branch_rows = []
    for branch_id in sorted(scoped):
        records = by_branch[branch_id]
        amount = sum((Decimal(f.cost) for f in records), ZERO)
        attributed += amount
        branch_rows.append({
            "sucursal_id": branch_id,
            "cost": float(amount),
            "clicks": sum(int(f.clicks) for f in records),
            "impressions": sum(int(f.impressions) for f in records),
            "free_pass_ads": float(sum((Decimal(f.free_pass_conversions) for f in records), ZERO)),
            "web_purchase_ads": float(sum((Decimal(f.web_purchase_conversions) for f in records), ZERO)),
        })
    complete = dates == {
        month_start + timedelta(days=i)
        for i in range((cutoff_date - month_start).days + 1)
    }
    result.update({
        "status": "complete" if complete else "partial",
        "complete_to_cutoff": complete,
        "covered_days": len(dates),
        "missing_days": result["expected_days"] - len(dates),
        "rows": branch_rows,
        "scope_attributed_cost": float(attributed),
        "observed_from": start.isoformat(),
        "observed_to": end.isoformat(),
    })
    if access.is_global:
        reconciliation = _valid_global_reconciliation(start, end, attributed)
        if reconciliation is None:
            return _empty("requires_review", month_start, cutoff_date)
        account, unassigned = reconciliation
        result.update({
            "account_cost_observed": float(account),
            "unassigned_cost_observed": float(unassigned),
            "account_reconciled": True,
        })
    return result


def combine_m5_m6(m5: dict, m6: dict, *, month_start: date, cutoff_date: date,
                  is_global: bool) -> dict:
    """Extend an intact M5 payload with an explicitly approved M6 segment.

    Do not turn pending M6 approval into zero cost. A failing M6 after approval
    fails closed for the whole combined attribution block.
    """
    if m6["status"] in ("unavailable", "pending_mapping", "scope_unavailable"):
        return m5
    if m6["status"] not in ("partial", "complete"):
        return _empty("requires_review", month_start, cutoff_date)
    if m5["status"] not in ("partial", "complete"):
        return m5

    original = {int(row["sucursal_id"]): row for row in m5["rows"]}
    incoming = {int(row["sucursal_id"]): row for row in m6["rows"]}
    if not original or set(original) != set(incoming):
        return _empty("requires_review", month_start, cutoff_date)
    if (
        m5.get("observed_to") != "2026-10-08"
        or m6.get("observed_from") != "2026-10-09"
    ):
        return _empty("requires_review", month_start, cutoff_date)
    rows = []
    for branch_id in sorted(original):
        a, b = original[branch_id], incoming[branch_id]
        rows.append({
            "sucursal_id": branch_id,
            **{field: float(Decimal(str(a[field])) + Decimal(str(b[field])))
               for field in ("cost", "clicks", "impressions",
                             "free_pass_ads", "web_purchase_ads")},
        })
    expected = (cutoff_date - month_start).days + 1
    covered = m5["covered_days"] + m6["covered_days"]
    combined = {
        **m5,
        "status": "complete" if covered == expected else "partial",
        "complete_to_cutoff": covered == expected,
        "covered_days": covered,
        "missing_days": expected - covered,
        "historical_to": END.isoformat(),
        "observed_to": m6["observed_to"],
        "rows": rows,
        "scope_attributed_cost": float(
            Decimal(str(m5["scope_attributed_cost"]))
            + Decimal(str(m6["scope_attributed_cost"]))
        ),
    }
    if is_global:
        if not all(
            item.get("account_reconciled") is True
            and item.get("account_cost_observed") is not None
            and item.get("unassigned_cost_observed") is not None
            for item in (m5, m6)
        ):
            return _empty("requires_review", month_start, cutoff_date)
        combined.update({
            field: float(Decimal(str(m5[field])) + Decimal(str(m6[field])))
            for field in ("account_cost_observed", "unassigned_cost_observed")
        })
        combined["account_reconciled"] = True
    else:
        for field in ("account_cost_observed", "unassigned_cost_observed",
                      "account_reconciled"):
            combined.pop(field, None)
    return combined
