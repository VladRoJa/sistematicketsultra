"""Published M6 13-Oct+ per-branch attribution; never read staged days.

Only a *canonical* daily pair is eligible. Restricted access queries group
facts through its authorized branch mappings, not the global account ledger.
The original M5 and M6 (09..12) attribution readers remain untouched.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased

from app.extensions import db
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.models.google_ads_m6_continuity import GoogleAdsBranchApprovedIdentityORM
from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM
from app.models.warehouse import TrackBranchCatalogORM, WarehouseUploadORM
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import load_visible_marketing_branches
from app.services.marketing_google_ads_m6_attribution_service import (
    CUSTOMER_ID, M5_REFERENCE, PER_DAY_CAMPAIGNS, PER_DAY_GROUPS,
    _load_m5, _mapping_rows, _valid_version, _version, _empty,
)

FIRST_DAILY_DAY = date(2026, 10, 13)
ZERO = Decimal("0")
METRICS = ("cost", "clicks", "impressions", "free_pass_ads", "web_purchase_ads")


def _fail(month_start: date, cutoff: date) -> dict:
    return _empty("requires_review", month_start, cutoff)


def _published_days(start: date, cutoff: date, version_id: int):
    """Publication/RAW metadata only: no cross-branch financial reads."""
    publication = GoogleAdsM6DailyPublicationORM
    campaign = aliased(WarehouseUploadORM)
    group = aliased(WarehouseUploadORM)
    return (
        db.session.query(publication, campaign, group)
        .join(campaign, campaign.id == publication.campaign_upload_id)
        .join(group, group.id == publication.ad_group_upload_id)
        .filter(
            publication.customer_id == CUSTOMER_ID,
            publication.approval_version_id == version_id,
            publication.is_canonical.is_(True),
            publication.business_date.between(start, cutoff),
        )
        .order_by(publication.business_date)
        .all()
    )


def _metadata_ok(pub, camp, group, day: date) -> bool:
    return (
        pub.business_date == day
        and pub.customer_id == CUSTOMER_ID
        and pub.is_canonical is True
        and pub.revision >= 1
        and pub.campaign_upload_id != pub.ad_group_upload_id
        and camp.id == pub.campaign_upload_id
        and group.id == pub.ad_group_upload_id
        and camp.status == group.status == "ACTIVE"
        and camp.source_file_deleted_at is None
        and group.source_file_deleted_at is None
        and camp.file_hash_sha256 == pub.campaign_sha256
        and group.file_hash_sha256 == pub.ad_group_sha256
        and camp.cutoff_date == group.cutoff_date == day
        and camp.date_from == camp.date_to == day
        and group.date_from == group.date_to == day
    )


def _restricted_group_facts(branch_ids: tuple[int, ...],
                            group_uploads: tuple[int, ...],
                            start: date, cutoff: date,
                            version_id: int):
    mapping = GoogleAdsBranchApprovedIdentityORM
    catalog = TrackBranchCatalogORM
    group = GoogleAdsAdGroupDailyMetricORM
    return (
        db.session.query(group, mapping, catalog)
        .join(mapping, and_(
            group.campaign_key == mapping.campaign_key,
            group.ad_group_key == mapping.ad_group_key,
            mapping.approval_version_id == version_id,
        ))
        .join(catalog, catalog.sucursal_canon == mapping.sucursal_canon)
        .filter(
            catalog.sucursal_id.in_(branch_ids),
            group.source_upload_id.in_(group_uploads),
            group.customer_id == CUSTOMER_ID,
            group.report_date.between(start, cutoff),
        )
        .all()
    )


def _valid_group_row(fact, mapping, pub, *, day: date) -> bool:
    return (
        fact.source_upload_id == pub.ad_group_upload_id
        and fact.report_date == day
        and fact.customer_id == CUSTOMER_ID
        and fact.source_kind == "WAREHOUSE_XLSX"
        and fact.currency_code == "MXN"
        and fact.campaign_id is None and fact.ad_group_id is None
        and fact.campaign_key == mapping.campaign_key
        and fact.ad_group_key == mapping.ad_group_key
    )


def _global_day_cost(pub, attributed: Decimal):
    """Global-only: exactly 27+43, no campaign/group spend double count."""
    camp = (
        db.session.query(GoogleAdsDailyMetricORM)
        .filter(
            GoogleAdsDailyMetricORM.customer_id == CUSTOMER_ID,
            GoogleAdsDailyMetricORM.report_date == pub.business_date,
            GoogleAdsDailyMetricORM.source_upload_id == pub.campaign_upload_id,
        ).all()
    )
    group = (
        db.session.query(GoogleAdsAdGroupDailyMetricORM)
        .filter(
            GoogleAdsAdGroupDailyMetricORM.customer_id == CUSTOMER_ID,
            GoogleAdsAdGroupDailyMetricORM.report_date == pub.business_date,
            GoogleAdsAdGroupDailyMetricORM.source_upload_id == pub.ad_group_upload_id,
        ).all()
    )
    if len(camp) != PER_DAY_CAMPAIGNS or len(group) != PER_DAY_GROUPS:
        return None
    if (len({row.campaign_key for row in camp}) != PER_DAY_CAMPAIGNS
            or len({(row.campaign_key, row.ad_group_key) for row in group})
            != PER_DAY_GROUPS):
        return None
    if any(row.currency_code != "MXN"
           or row.source_kind != "WAREHOUSE_XLSX"
           or row.campaign_id is not None for row in camp):
        return None
    if any(row.currency_code != "MXN"
           or row.source_kind != "WAREHOUSE_XLSX"
           or row.campaign_id is not None
           or row.ad_group_id is not None for row in group):
        return None
    camp_cost = sum((Decimal(row.cost) for row in camp), ZERO)
    group_cost = sum((Decimal(row.cost) for row in group), ZERO)
    if (
        camp_cost != group_cost
        or camp_cost < attributed
        or sum(int(row.clicks) for row in camp) !=
           sum(int(row.clicks) for row in group)
        or sum(int(row.impressions) for row in camp) !=
           sum(int(row.impressions) for row in group)
        or abs(sum((Decimal(row.conversions) for row in camp), ZERO)
               - sum((Decimal(row.conversions) for row in group), ZERO))
        > Decimal("0.01")
    ):
        return None
    return camp_cost


def read_google_ads_m6_daily_branch_attribution(
    *, month_start: date, cutoff_date: date, access: MarketingAccess,
) -> dict:
    """Read only a contiguous prefix of canonical daily uploads from 13-Oct."""
    if cutoff_date < month_start or month_start.day != 1:
        raise ValueError("Rango M6 diario inválido")
    result = _empty("unavailable", month_start, cutoff_date)
    start = max(month_start, FIRST_DAILY_DAY)
    if start > cutoff_date:
        return result

    _, branch_ids, _ = load_visible_marketing_branches(access)
    if not branch_ids:
        return _empty("scope_unavailable", month_start, cutoff_date)
    version_rows = _version()
    if not version_rows:
        return _empty("pending_mapping", month_start, cutoff_date)
    if len(version_rows) != 1 or not _valid_version(version_rows[0]):
        return _fail(month_start, cutoff_date)
    version = version_rows[0]
    try:
        manifest = _load_m5()
    except (RuntimeError, ValueError, OSError, KeyError):
        return _fail(month_start, cutoff_date)
    approved = {
        (row[2], row[3]): (row[4], int(row[5]))
        for row in manifest["rows"]
    }
    if (manifest.get("id") != M5_REFERENCE
            or manifest.get("customer_id") != CUSTOMER_ID
            or len(approved) != 26):
        return _fail(month_start, cutoff_date)

    scoped = {}
    for mapping, catalog, branch in _mapping_rows(version.id, branch_ids):
        branch_id = int(catalog.sucursal_id)
        if (
            mapping.approval_version_id != version.id
            or approved.get((mapping.campaign_key, mapping.ad_group_key))
            != (mapping.sucursal_canon, branch_id)
            or catalog.is_track_active is not True
            or branch.operational_status != "ACTIVA"
            or branch_id in scoped
        ):
            return _fail(month_start, cutoff_date)
        scoped[branch_id] = mapping
    if not scoped or set(scoped) != set(branch_ids):
        return _empty("pending_mapping", month_start, cutoff_date)
    if access.is_global and len(scoped) != 26:
        return _fail(month_start, cutoff_date)

    pub_rows = _published_days(start, cutoff_date, version.id)
    if not pub_rows:
        return result
    pubs = {}
    for pub, campaign_raw, group_raw in pub_rows:
        day = pub.business_date
        if day in pubs or not _metadata_ok(pub, campaign_raw, group_raw, day):
            return _fail(month_start, cutoff_date)
        pubs[day] = pub
    last = max(pubs)
    expected = {
        start + timedelta(days=i) for i in range((last - start).days + 1)
    }
    # No gaps between the first daily cut and the last publication.
    if set(pubs) != expected:
        return _fail(month_start, cutoff_date)

    facts = _restricted_group_facts(
        tuple(sorted(scoped)),
        tuple(sorted({p.ad_group_upload_id for p in pubs.values()})),
        start, last, version.id,
    )
    by_branch_day = {}
    for fact, mapping, catalog in facts:
        bid = int(catalog.sucursal_id)
        key = (bid, fact.report_date)
        pub = pubs.get(fact.report_date)
        if (
            bid not in scoped or pub is None
            or mapping.id != scoped[bid].id
            or key in by_branch_day
            or not _valid_group_row(fact, mapping, pub, day=fact.report_date)
        ):
            return _fail(month_start, cutoff_date)
        by_branch_day[key] = fact
    if any((bid, day) not in by_branch_day
           for bid in scoped for day in expected):
        return _fail(month_start, cutoff_date)

    rows, attributed = [], ZERO
    by_date_attributed = defaultdict(lambda: ZERO)
    for bid in sorted(scoped):
        metrics = [by_branch_day[bid, day] for day in sorted(expected)]
        branch_cost = sum((Decimal(f.cost) for f in metrics), ZERO)
        attributed += branch_cost
        for fact in metrics:
            by_date_attributed[fact.report_date] += Decimal(fact.cost)
        rows.append({
            "sucursal_id": bid, "cost": float(branch_cost),
            "clicks": sum(int(f.clicks) for f in metrics),
            "impressions": sum(int(f.impressions) for f in metrics),
            "free_pass_ads": float(sum(
                (Decimal(f.free_pass_conversions) for f in metrics), ZERO)),
            "web_purchase_ads": float(sum(
                (Decimal(f.web_purchase_conversions) for f in metrics), ZERO)),
        })
    complete = len(expected) == (cutoff_date - month_start).days + 1
    result.update({
        "status": "complete" if complete else "partial",
        "complete_to_cutoff": complete,
        "covered_days": len(expected),
        "missing_days": result["expected_days"] - len(expected),
        "rows": rows, "scope_attributed_cost": float(attributed),
        "observed_from": start.isoformat(), "observed_to": last.isoformat(),
        "historical_to": last.isoformat(),
    })
    if access.is_global:
        account = ZERO
        for day in sorted(expected):
            amount = _global_day_cost(pubs[day], by_date_attributed[day])
            if amount is None:
                return _fail(month_start, cutoff_date)
            account += amount
        result.update({
            "account_cost_observed": float(account),
            "unassigned_cost_observed": float(account - attributed),
            "account_reconciled": True,
        })
    return result


def combine_historical_with_daily(
    historical: dict, daily: dict, *, month_start: date,
    cutoff_date: date, is_global: bool,
) -> dict:
    """Append a contiguous canonical daily prefix without changing M5/M6."""
    if daily["status"] in ("unavailable", "scope_unavailable", "pending_mapping"):
        return historical
    if daily["status"] not in ("partial", "complete"):
        return _fail(month_start, cutoff_date)
    if historical["status"] not in ("partial", "complete"):
        return _fail(month_start, cutoff_date)
    if (historical.get("observed_to") != "2026-10-12"
            or daily.get("observed_from") != "2026-10-13"):
        return _fail(month_start, cutoff_date)
    older = {int(r["sucursal_id"]): r for r in historical["rows"]}
    newer = {int(r["sucursal_id"]): r for r in daily["rows"]}
    if not older or set(older) != set(newer):
        return _fail(month_start, cutoff_date)
    rows = []
    for bid in sorted(older):
        rows.append({
            "sucursal_id": bid,
            **{
                field: float(Decimal(str(older[bid][field]))
                             + Decimal(str(newer[bid][field])))
                for field in METRICS
            },
        })
    days = historical["covered_days"] + daily["covered_days"]
    expected = (cutoff_date - month_start).days + 1
    result = {
        **historical, "status": "complete" if days == expected else "partial",
        "complete_to_cutoff": days == expected,
        "covered_days": days, "expected_days": expected,
        "missing_days": expected - days,
        "historical_to": daily["observed_to"],
        "observed_to": daily["observed_to"],
        "rows": rows,
        "scope_attributed_cost": float(
            Decimal(str(historical["scope_attributed_cost"]))
            + Decimal(str(daily["scope_attributed_cost"]))),
    }
    if is_global:
        if not all(item.get("account_reconciled") is True for item in
                   (historical, daily)):
            return _fail(month_start, cutoff_date)
        for field in ("account_cost_observed", "unassigned_cost_observed"):
            result[field] = float(
                Decimal(str(historical[field])) + Decimal(str(daily[field])))
        result["account_reconciled"] = True
    else:
        for field in ("account_cost_observed", "unassigned_cost_observed",
                      "account_reconciled"):
            result.pop(field, None)
    return result
