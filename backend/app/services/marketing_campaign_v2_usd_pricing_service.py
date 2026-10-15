"""Campaign V2: versioned iVentas USD price reference, charged on delivered messages.

This is an operator-established estimate from iVentas reports, NOT a quote
or confirmation of billing. It must never be used as an FX/MXN conversion.
Historical MXN approvals keep using their original budget contract.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from typing import Any

USD_RATE_VERSION = "IVENTAS_MX_DELIVERED_USD_V1"
USD_PER_DELIVERED = Decimal("0.0542")
FOUR_DP = Decimal("0.0001")


def _usd(amount: Decimal) -> str:
    return format(amount.quantize(FOUR_DP, rounding=ROUND_HALF_UP), ".4f")


def estimate_automatic_usd_maximum(*, plan: Any) -> dict[str, Any]:
    """Maximum if every sendable recipient gets one *billable* delivery.

    No channel-level quotation, exchange rate, or database write. The quota
    assessment is independent. The digest binds rate version and exact plan.
    """
    batches = tuple(plan.batches)
    count = len(plan.sendable_phones)
    assigned = sum(len(batch.recipients) for batch in batches)
    unassigned = max(0, count - assigned)
    complete = bool(plan.ready and batches and assigned == count)
    items = [
        {
            "sucursal_canon": str(batch.sucursal_canon),
            "channel_id": str(batch.provider_channel_id or ""),
            "recipients": len(batch.recipients),
            "maximum_estimated_usd": _usd(
                USD_PER_DELIVERED * len(batch.recipients)
            ),
        }
        for batch in batches
    ]
    fingerprint = hashlib.sha256(json.dumps({
        "version": "AUTO_USD_MAXIMUM_V1",
        "campaign_id": plan.campaign_id,
        "dispatch_fingerprint": plan.dispatch_fingerprint,
        "rate_version": USD_RATE_VERSION,
        "unit_usd": _usd(USD_PER_DELIVERED),
        "billable_basis": "PROVIDER_CONFIRMED_DELIVERED",
        "status": complete,
        "batches": items,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "quote_fingerprint": fingerprint,
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "currency": "USD",
        "basis": "AUTOMATIC_MAXIMUM_IF_ALL_RECIPIENTS_DELIVERED",
        "billable_basis": "PROVIDER_CONFIRMED_DELIVERED",
        "rate_version": USD_RATE_VERSION,
        "unit_cost_usd": _usd(USD_PER_DELIVERED),
        "sendable_recipients": count,
        "unassigned_recipients": unassigned,
        "maximum_estimated_usd": _usd(USD_PER_DELIVERED * count),
        "batches": items,
    }


def calculate_delivered_cost_usd(*, billed_deliveries: int) -> str:
    """Indicative USD calculation only; provider-reported billed cost wins."""
    if type(billed_deliveries) is not int or billed_deliveries < 0:
        raise ValueError("Se requiere cantidad entera de entregados cobrados.")
    return _usd(USD_PER_DELIVERED * billed_deliveries)
