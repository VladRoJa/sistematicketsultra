"""Worker persistence + ACL-safe read-only cache for M2 monthly sale correlations.

No HTTP request performs Warehouse scans. Cache is keyed by sale dates and
attribution window. A cached PENDING never masquerades as zero conversions.
Only aggregates (no phones, recipient IDs, or individual orders) are stored.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2CommercialSaleMonthORM,
    MarketingCampaignV2ORM,
)
from app.services.marketing_campaign_v2_query_service import (
    _campaign_visible_to_scope,
    _normalize_current_scope,
)
from app.services.marketing_campaign_v2_sales_month_source_service import (
    _month_window,
    reconcile_sale_month,
)


def materialize_sale_month(
    *, from_date: str, to_date: str, window_days: int,
    checked_at: datetime, session=None,
) -> dict:
    """Explicit worker-only write; never called from a request handler."""
    first, last, *_ = _month_window(from_date, to_date, window_days=window_days)
    if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
        raise ValueError("checked_at debe ser datetime con zona horaria.")
    active = session if session is not None else db.session
    payload = reconcile_sale_month(
        from_date=first.isoformat(), to_date=last.isoformat(),
        window_days=window_days, session=active,
    )
    # Fail closed if a future adapter accidentally returns sensitive records.
    forbidden = ("allocations_private", "phone_mx10", "normalized_phone", "recipient_id")
    if any(key in payload for key in forbidden):
        raise ValueError("M2 produjo campos de identidad no autorizados para caché.")
    identity = (first, last, window_days)
    record = active.get(MarketingCampaignV2CommercialSaleMonthORM, identity)
    if record is None:
        record = MarketingCampaignV2CommercialSaleMonthORM(
            sale_from=first, sale_to=last, window_days=window_days,
        )
        active.add(record)
    record.status = payload["status"]
    record.result_json = payload
    record.checked_at = checked_at.astimezone(timezone.utc)
    active.commit()
    return {
        "status": payload["status"],
        "sale_from": first.isoformat(), "sale_to": last.isoformat(),
        "window_days": window_days,
        "materialized": True,
    }


def read_sale_month_cache(
    *, from_date: str, to_date: str, window_days: int,
    allowed_sucursal_keys: Iterable[str] | None, session=None,
) -> dict:
    """Return only visible campaigns; never leak unrelated branch totals."""
    first, last, *_ = _month_window(from_date, to_date, window_days=window_days)
    active = session if session is not None else db.session
    base = {
        "from": first.isoformat(), "to": last.isoformat(),
        "window_days": window_days,
        "source": "VENTA_TOTAL_CANONICAL_SALE_MONTH",
        "attribution": "LAST_PROVEN_SUBMISSION_NON_CAUSAL",
        "buyers_observed": None,
        "transactions_observed": None,
        "revenue_observed_mxn": None,
        "cost_mxn": None,
        "roas": None,
        "campaigns": [],
        "timezone": "America/Tijuana",
    }
    record = active.get(
        MarketingCampaignV2CommercialSaleMonthORM,
        (first, last, window_days),
    )
    if record is None:
        return {**base, "status": "NOT_MATERIALIZED", "checked_at": None}
    checked = record.checked_at
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    base["checked_at"] = checked.astimezone(timezone.utc).isoformat()
    if record.status != "READY":
        return {**base, "status": record.status}
    payload = record.result_json or {}
    if (payload.get("status") != "READY"
            or payload.get("from") != first.isoformat()
            or payload.get("to") != last.isoformat()
            or payload.get("window_days") != window_days):
        return {**base, "status": "STALE_CACHE"}
    rows = list(payload.get("campaigns") or [])
    if not rows:
        return {**base, "status": "READY",
                "buyers_observed": 0, "transactions_observed": 0,
                "revenue_observed_mxn": "0.00"}
    ids = {int(item["campaign_id"]) for item in rows}
    scope = _normalize_current_scope(allowed_sucursal_keys)
    campaigns = active.query(MarketingCampaignV2ORM).filter(
        MarketingCampaignV2ORM.id.in_(sorted(ids))
    ).all()
    visible = {
        int(c.id): str(c.name)
        for c in campaigns
        if _campaign_visible_to_scope(c, scope)
    }
    selected = [
        {**item, "name": visible[int(item["campaign_id"])]}
        for item in rows if int(item["campaign_id"]) in visible
    ]
    # Transactions are allocated once globally, so summing visible campaign
    # transactions is safe. Unique global buyers cannot be summed across campaigns.
    revenue = sum(
        (Decimal(str(row["revenue_observed_mxn"])) for row in selected),
        Decimal("0"),
    )
    total_transactions = sum(int(row["transactions_observed"]) for row in selected)
    total_buyers = (
        int(payload["buyers_observed"])
        if len(visible) == len(ids) and payload.get("buyers_observed") is not None
        else None
    )
    return {
        **base, "status": "READY",
        "campaigns": sorted(selected, key=lambda item: int(item["campaign_id"])),
        "buyers_observed": total_buyers,
        "transactions_observed": total_transactions,
        "revenue_observed_mxn": format(revenue.quantize(Decimal("0.01")), ".2f"),
        "buyer_count_note": (
            "Compradores globales únicos" if total_buyers is not None
            else "Compradores globales no disponibles para alcance parcial"
        ),
        "sale_snapshot_id": payload.get("sale_snapshot_id"),
        "sale_business_date": payload.get("sale_business_date"),
        "rule_version": payload.get("rule_version"),
        "evidence_status": "COMPLETE",
    }
