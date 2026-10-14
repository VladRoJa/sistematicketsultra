"""Account-level Google Ads evidence for the Funnel.

Campaigns from this source span multiple branches; never allocate their spend
to branches/regions by inference. This service never affects Funnel cutoffs.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import os
import re

from sqlalchemy import func, and_, or_, exists
from sqlalchemy.orm import aliased

from app.extensions import db
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM
from app.models.google_ads_m6_continuity import GoogleAdsBranchApprovalVersionORM
from app.models.warehouse import WarehouseUploadORM
from app.warehouse.services.google_ads_m6_continuity_approval_service import (
    M6_REFERENCE, M5_REFERENCE, CAMPAIGN_UPLOAD_ID, GROUP_UPLOAD_ID,
)


M6_FIRST_DAILY_DAY = date(2026, 10, 13)


def _canonical_m6_campaign_filter():
    """Correlated fail-closed gate: only explicitly canonical daily M6 uploads.

    A RAW or a structured row is never itself a publication. Canonical rows
    must match BOTH original Warehouse upload hashes and the approved M6 version.
    No daily publication is seeded by a successful import.
    """
    fact = GoogleAdsDailyMetricORM
    day = GoogleAdsM6DailyPublicationORM
    raw = WarehouseUploadORM
    group_raw = aliased(WarehouseUploadORM)
    approval = GoogleAdsBranchApprovalVersionORM
    authorized = exists().where(and_(
        day.customer_id == fact.customer_id,
        day.business_date == fact.report_date,
        day.campaign_upload_id == fact.source_upload_id,
        day.is_canonical.is_(True),
        fact.source_kind == "WAREHOUSE_XLSX",
        raw.id == day.campaign_upload_id,
        raw.status == "ACTIVE",
        raw.source_file_deleted_at.is_(None),
        raw.file_hash_sha256 == day.campaign_sha256,
        raw.date_from == day.business_date,
        raw.date_to == day.business_date,
        # The published pair ceases to be valid when EITHER RAW is archived,
        # deleted or replaced. Never expose global campaign spend while the
        # group evidence fails integrity, even if the campaign RAW is intact.
        group_raw.id == day.ad_group_upload_id,
        group_raw.status == "ACTIVE",
        group_raw.source_file_deleted_at.is_(None),
        group_raw.file_hash_sha256 == day.ad_group_sha256,
        group_raw.date_from == day.business_date,
        group_raw.date_to == day.business_date,
        approval.id == day.approval_version_id,
        approval.customer_id == day.customer_id,
        approval.approval_reference == M6_REFERENCE,
        approval.source_approval_reference == M5_REFERENCE,
        approval.source_campaign_upload_id == CAMPAIGN_UPLOAD_ID,
        approval.source_ad_group_upload_id == GROUP_UPLOAD_ID,
        approval.valid_from <= day.business_date,
        or_(approval.valid_to.is_(None),
            approval.valid_to >= day.business_date),
        approval.approved_by_user_id.is_not(None),
    )).correlate(fact)
    return or_(fact.report_date < M6_FIRST_DAILY_DAY, authorized)


def read_google_ads_funnel_investment(
    *, month_start: date, cutoff_date: date, is_global: bool
) -> dict:
    """Return scoped monthly-to-cutoff evidence, or no financial data."""
    if not is_global:
        return {
            "status": "scope_unavailable",
            "reason": "Campañas multiclub sin distribución validada por sucursal.",
            "currency": "MXN",
            "amount": None,
            "complete_to_cutoff": False,
        }

    customer_id = os.environ.get("GOOGLE_ADS_OAUTH_CUSTOMER_ID", "").replace("-", "").strip()
    if not re.fullmatch(r"[0-9]{10}", customer_id):
        return {
            "status": "not_configured",
            "currency": "MXN",
            "amount": None,
            "complete_to_cutoff": False,
        }

    rows = (
        db.session.query(
            GoogleAdsDailyMetricORM.report_date,
            func.sum(GoogleAdsDailyMetricORM.cost).label("cost"),
            func.sum(GoogleAdsDailyMetricORM.clicks).label("clicks"),
            func.sum(GoogleAdsDailyMetricORM.impressions).label("impressions"),
            func.sum(GoogleAdsDailyMetricORM.conversions).label("conversions"),
            func.count(GoogleAdsDailyMetricORM.id).label("campaign_rows"),
        )
        .filter(
            GoogleAdsDailyMetricORM.customer_id == customer_id,
            GoogleAdsDailyMetricORM.currency_code == "MXN",
            GoogleAdsDailyMetricORM.report_date >= month_start,
            GoogleAdsDailyMetricORM.report_date <= cutoff_date,
            *([_canonical_m6_campaign_filter()]
              if cutoff_date >= M6_FIRST_DAILY_DAY else []),
        )
        .group_by(GoogleAdsDailyMetricORM.report_date)
        .order_by(GoogleAdsDailyMetricORM.report_date.asc())
        .all()
    )
    if not rows:
        return {
            "status": "no_data",
            "currency": "MXN",
            "amount": None,
            "complete_to_cutoff": False,
        }

    # Even a manually marked day must have all 27 campaigns; 1..12-OCT is
    # historical and retains its original read behavior.
    if any(
        row.report_date >= M6_FIRST_DAILY_DAY
        and int(row.campaign_rows) != 27
        for row in rows
    ):
        return {
            "status": "requires_review",
            "currency": "MXN", "amount": None,
            "complete_to_cutoff": False,
            "reason": "M6_CANONICAL_CAMPAIGN_COVERAGE_FAILED",
        }

    dates = {row.report_date for row in rows}
    expected = {
        month_start + timedelta(days=offset)
        for offset in range((cutoff_date - month_start).days + 1)
    }
    complete = dates == expected
    return {
        "status": "complete" if complete else "partial",
        "currency": "MXN",
        "amount": float(sum((Decimal(row.cost) for row in rows), Decimal("0"))),
        "clicks": sum(int(row.clicks) for row in rows),
        "impressions": sum(int(row.impressions) for row in rows),
        "conversions": float(
            sum((Decimal(row.conversions) for row in rows), Decimal("0"))
        ),
        "data_from": min(dates).isoformat(),
        "data_to": max(dates).isoformat(),
        "requested_from": month_start.isoformat(),
        "requested_to": cutoff_date.isoformat(),
        "covered_days": len(dates),
        "expected_days": len(expected),
        "missing_days": len(expected - dates),
        "complete_to_cutoff": complete,
        "scope": "GOOGLE_ADS_ACCOUNT",
        "allocation": "UNASSIGNED_TO_BRANCHES",
        "source": "WAREHOUSE_XLSX_OR_API",
    }


def build_funnel_investment_sources(
    *, meta_assigned: float | None, google_ads: dict
) -> dict:
    """Only publish a comparable combined amount when Google covers the cutoff."""
    full_coverage = google_ads.get("complete_to_cutoff") is True
    google_amount = google_ads.get("amount")
    combined = (
        float(Decimal(str(meta_assigned)) + Decimal(str(google_amount)))
        if meta_assigned is not None and google_amount is not None and full_coverage
        else None
    )
    return {
        "meta_assigned": meta_assigned,
        "google_ads": google_ads,
        "combined": combined,
        "combined_available": combined is not None,
        "combined_definition": "Meta asignada a clubes + Google Ads de cuenta; no incluye Meta sin asignación.",
        "existing_cpl_cpt_cac_basis": "META_ASSIGNED_ONLY",
    }
