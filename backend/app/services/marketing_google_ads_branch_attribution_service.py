"""M5 Google Ads historical attribution: read-only, scoped, provisional.

Not wired to the Funnel or an endpoint yet. Never allocate Google Ads
account spend twice, and never infer a branch from an ad-group name.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_

from app.extensions import db
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.models.google_ads_branch_identity_mapping import (
    GoogleAdsBranchIdentityMappingORM,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchCatalogORM
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.warehouse.services.google_ads_m5_identity_seed_service import (
    _load as _load_approved_manifest,
    _validate_source as _validate_historical_source,
)

HISTORICAL_START = date(2026, 9, 24)
HISTORICAL_END = date(2026, 10, 8)
CUSTOMER_ID = "2739125201"
UPLOAD_ID = 21499
APPROVAL_REFERENCE = "GOOGLE_ADS_M5_IDENTITY_20261012_V1"
APPROVAL_STATUS = "APPROVED_PROVISIONAL_XLSX"
ZERO = Decimal("0")


def _empty(status: str, *, month_start: date, cutoff_date: date) -> dict:
    return {
        "status": status,
        "currency": "MXN",
        "allocation_basis": APPROVAL_STATUS,
        "requested_from": month_start.isoformat(),
        "requested_to": cutoff_date.isoformat(),
        "historical_from": HISTORICAL_START.isoformat(),
        "historical_to": HISTORICAL_END.isoformat(),
        "complete_to_cutoff": False,
        "covered_days": 0,
        "expected_days": (cutoff_date - month_start).days + 1,
        "missing_days": (cutoff_date - month_start).days + 1,
        "rows": [],
        "scope_attributed_cost": None,
    }


def _load_scoped_mapping_rows(branch_ids: tuple[int, ...]):
    return (
        db.session.query(
            GoogleAdsBranchIdentityMappingORM,
            TrackBranchCatalogORM,
            Sucursal,
        )
        .join(
            TrackBranchCatalogORM,
            TrackBranchCatalogORM.sucursal_canon
            == GoogleAdsBranchIdentityMappingORM.sucursal_canon,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id == TrackBranchCatalogORM.sucursal_id,
        )
        .filter(TrackBranchCatalogORM.sucursal_id.in_(branch_ids))
        .all()
    )


def _load_scoped_fact_rows(
    *, branch_ids: tuple[int, ...], start: date, end: date,
):
    mapping = GoogleAdsBranchIdentityMappingORM
    fact = GoogleAdsAdGroupDailyMetricORM
    catalog = TrackBranchCatalogORM
    return (
        db.session.query(fact, mapping, catalog)
        .join(
            mapping,
            and_(
                fact.customer_id == mapping.customer_id,
                fact.campaign_key == mapping.campaign_key,
                fact.ad_group_key == mapping.ad_group_key,
                fact.source_upload_id == mapping.source_upload_id,
                fact.report_date >= mapping.valid_from,
                fact.report_date <= mapping.valid_to,
            ),
        )
        .join(catalog, catalog.sucursal_canon == mapping.sucursal_canon)
        .filter(
            catalog.sucursal_id.in_(branch_ids),
            fact.customer_id == CUSTOMER_ID,
            fact.source_upload_id == UPLOAD_ID,
            fact.report_date.between(start, end),
        )
        .all()
    )


def _load_global_ledger_rows(start: date, end: date):
    """Never call on an access-restricted request."""
    return (
        db.session.query(GoogleAdsDailyMetricORM)
        .filter(
            GoogleAdsDailyMetricORM.customer_id == CUSTOMER_ID,
            GoogleAdsDailyMetricORM.currency_code == "MXN",
            GoogleAdsDailyMetricORM.report_date.between(start, end),
        )
        .all()
    )


def _mapping_ok(mapping, catalog, branch) -> bool:
    return all((
        mapping.customer_id == CUSTOMER_ID,
        mapping.source_upload_id == UPLOAD_ID,
        mapping.valid_from == HISTORICAL_START,
        mapping.valid_to == HISTORICAL_END,
        mapping.approval_status == APPROVAL_STATUS,
        mapping.approval_reference == APPROVAL_REFERENCE,
        mapping.approved_on == date(2026, 10, 12),
        mapping.sucursal_canon == catalog.sucursal_canon,
        catalog.is_track_active is True,
        catalog.sucursal_id == branch.sucursal_id,
        branch.operational_status == "ACTIVA",
    ))


def _fact_ok(fact, mapping, catalog) -> bool:
    return all((
        fact.customer_id == CUSTOMER_ID,
        fact.source_kind == "WAREHOUSE_XLSX",
        fact.source_upload_id == UPLOAD_ID,
        fact.currency_code == "MXN",
        fact.campaign_id is None,
        fact.ad_group_id is None,
        fact.campaign_key == mapping.campaign_key,
        fact.ad_group_key == mapping.ad_group_key,
        fact.customer_id == mapping.customer_id,
        fact.source_upload_id == mapping.source_upload_id,
        fact.report_date >= mapping.valid_from,
        fact.report_date <= mapping.valid_to,
        mapping.sucursal_canon == catalog.sucursal_canon,
    ))


def read_google_ads_branch_attribution(
    *, month_start: date, cutoff_date: date, access: MarketingAccess,
) -> dict:
    """Return separately scoped historical group metrics, never Funnel totals.

    In non-global access, SQL queries cover only permitted branches and
    NEVER inspect the account ledger or unassigned facts. Unknown or
    altered mappings fail closed. A partial month is explicitly partial.
    """
    if cutoff_date < month_start or month_start.day != 1:
        raise ValueError("Rango M5 inválido: mes/corte.")

    result = _empty("unavailable", month_start=month_start, cutoff_date=cutoff_date)
    _branches, branch_ids, _scope = load_visible_marketing_branches(access)
    if not branch_ids:
        result["status"] = "scope_unavailable"
        return result

    start = max(month_start, HISTORICAL_START)
    end = min(cutoff_date, HISTORICAL_END)
    if start > end:
        return result

    mappings = _load_scoped_mapping_rows(branch_ids)
    scoped = {}
    for mapping, catalog, branch in mappings:
        branch_id = int(catalog.sucursal_id)
        if not _mapping_ok(mapping, catalog, branch) or branch_id in scoped:
            result["status"] = "requires_review"
            return result
        scoped[branch_id] = mapping

    # No approved mapping is not a zero-cost campaign.
    if not scoped:
        result["status"] = "pending_mapping"
        return result

    if access.is_global:
        # This validation reads global M3 and account-ledger evidence ONLY
        # for globally authorized requests.
        try:
            _validate_historical_source(
                db.session.connection(), _load_approved_manifest(),
            )
        except RuntimeError:
            result["status"] = "requires_review"
            return result

    rows = _load_scoped_fact_rows(
        branch_ids=tuple(sorted(scoped)), start=start, end=end,
    )
    by_branch = defaultdict(list)
    seen = set()
    for fact, mapping, catalog in rows:
        branch_id = int(catalog.sucursal_id)
        key = (branch_id, fact.report_date)
        if (
            branch_id not in scoped
            or not _fact_ok(fact, mapping, catalog)
            or mapping.id != scoped[branch_id].id
            or key in seen
        ):
            result["status"] = "requires_review"
            return result
        seen.add(key)
        by_branch[branch_id].append(fact)

    observed_dates = {start + timedelta(days=i) for i in range((end - start).days + 1)}
    if any(
        {row.report_date for row in by_branch.get(branch_id, [])} != observed_dates
        for branch_id in scoped
    ):
        result["status"] = "requires_review"
        return result

    local_total = ZERO
    output = []
    for branch_id in sorted(scoped):
        facts = by_branch[branch_id]
        cost = sum((Decimal(f.cost) for f in facts), ZERO)
        local_total += cost
        output.append({
            "sucursal_id": branch_id,
            "cost": float(cost),
            "clicks": sum(int(f.clicks) for f in facts),
            "impressions": sum(int(f.impressions) for f in facts),
            "free_pass_ads": float(sum((Decimal(f.free_pass_conversions) for f in facts), ZERO)),
            "web_purchase_ads": float(sum((Decimal(f.web_purchase_conversions) for f in facts), ZERO)),
        })

    requested_dates = {
        month_start + timedelta(days=i)
        for i in range((cutoff_date - month_start).days + 1)
    }
    complete = observed_dates == requested_dates
    result.update({
        "status": "complete" if complete else "partial",
        "complete_to_cutoff": complete,
        "covered_days": len(observed_dates),
        "missing_days": len(requested_dates - observed_dates),
        "rows": output,
        "scope_attributed_cost": float(local_total),
        "observed_from": start.isoformat(),
        "observed_to": end.isoformat(),
    })

    if access.is_global:
        ledger = _load_global_ledger_rows(start, end)
        account_by_date = defaultdict(lambda: ZERO)
        for row in ledger:
            if row.report_date not in observed_dates or row.currency_code != "MXN":
                result.update(_empty("requires_review", month_start=month_start, cutoff_date=cutoff_date))
                return result
            account_by_date[row.report_date] += Decimal(row.cost)
        if set(account_by_date) != observed_dates:
            result.update(_empty("requires_review", month_start=month_start, cutoff_date=cutoff_date))
            return result
        account_total = sum(account_by_date.values(), ZERO)
        unassigned = account_total - local_total
        if unassigned < ZERO:
            result.update(_empty("requires_review", month_start=month_start, cutoff_date=cutoff_date))
            return result
        result["account_cost_observed"] = float(account_total)
        result["unassigned_cost_observed"] = float(unassigned)
        result["account_reconciled"] = True

    return result
