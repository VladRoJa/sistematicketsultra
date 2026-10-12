"""Account-level Google Ads evidence for the Funnel.

Campaigns from this source span multiple branches; never allocate their spend
to branches/regions by inference. This service never affects Funnel cutoffs.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import os
import re

from sqlalchemy import func

from app.extensions import db
from app.models.google_ads_daily import GoogleAdsDailyMetricORM


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
        )
        .filter(
            GoogleAdsDailyMetricORM.customer_id == customer_id,
            GoogleAdsDailyMetricORM.currency_code == "MXN",
            GoogleAdsDailyMetricORM.report_date >= month_start,
            GoogleAdsDailyMetricORM.report_date <= cutoff_date,
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
