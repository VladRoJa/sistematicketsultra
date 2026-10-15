"""Campaign V2 capacity contract: no manual quota for regular branches.

Insurgentes and Independencia have independent 250-message rolling 24-hour
limits, enforced per provider channel. This is NOT a Meta balance, nor proof
of channel->portfolio mapping. Persisted approvals keep their original basis.

Only Suite-observed attempts/reservations can be counted: unresolvable
provider outcomes fail closed for the restricted channels. Does not send.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.marketing import (
    MarketingCampaignV2ProviderCampaignORM as Child,
    MarketingCampaignV2CapacityReservationORM as Reservation,
    MarketingCampaignV2DispatchApprovalORM as Approval,
)
from app.services.marketing_campaign_v2_operational_capacity_service import (
    POSSIBLY_ATTEMPTED, UNRESOLVED,
)

BASIS = "SUITE_BRANCH_EXCEPTION_CAPS_V1"
WINDOW = timedelta(hours=24)
RESTRICTED_BRANCHES = frozenset({"INDEPENDENCIA", "INSURGENTES"})
# Exact iVentas channel IDs grounded in Alembic f3c8a1b2d4e6.
# Protect both canonical branch identity and provider identity so neither a
# branch-label change nor a binding reassignment silently removes a 250 cap.
RESTRICTED_CHANNEL_IDS = frozenset({
    "6a29c8ffe83fa20008b5a789",  # INDEPENDENCIA
    "6a2aff2d555186000912586d",  # INSURGENTES
})
RESTRICTED_CHANNEL_LIMIT = 250


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _branch_key(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def restricted_branch(value: Any, channel_id: Any = None) -> bool:
    return (_branch_key(value) in RESTRICTED_BRANCHES or
            str(channel_id or "").strip() in RESTRICTED_CHANNEL_IDS)


def assess_branch_exception_capacity(
    *, plan: Any, session: Any, now: datetime,
    ignore_campaign_id: int | None = None,
) -> dict[str, Any]:
    """Read-only check; caller obtains advisory locks and checks again.

    Never trust a browser-supplied status or quota. Missing channel identities
    fail closed, including on regular branches.
    """
    timestamp = _utc(now)
    cutoff = timestamp - WINDOW
    limited_channels = {
        str(batch.provider_channel_id)
        for batch in plan.batches
        if restricted_branch(batch.sucursal_canon, batch.provider_channel_id) and batch.provider_channel_id
    }
    attempted = defaultdict(int)
    reserved = defaultdict(int)
    uncertain = set()

    if limited_channels:
        events = session.query(Child).filter(
            Child.provider == "IVENTAS",
            Child.provider_channel_id.in_(sorted(limited_channels)),
            Child.status.in_(sorted(POSSIBLY_ATTEMPTED)),
        ).all()
        for evt in events:
            if ignore_campaign_id is not None and int(evt.campaign_v2_id) == int(ignore_campaign_id):
                continue
            if (evt.status == "PROVIDER_ERROR" and
                    evt.reconciliation_resolution == "NOT_CREATED_CONFIRMED"):
                continue
            channel = str(evt.provider_channel_id)
            attempt_at = evt.submit_started_at or evt.submitted_at or evt.created_at
            if attempt_at is None:
                uncertain.add(channel)
                continue
            age = _utc(attempt_at)
            if age > timestamp or (evt.status in UNRESOLVED and age < cutoff):
                uncertain.add(channel)
                continue
            if age < cutoff:
                continue
            if type(evt.recipient_count) is not int or evt.recipient_count <= 0:
                uncertain.add(channel)
                continue
            attempted[channel] += evt.recipient_count

        active = session.query(Reservation).join(
            Approval, Approval.id == Reservation.approval_id,
        ).filter(
            Reservation.reserved_until > timestamp,
            Reservation.scope_kind == "CHANNEL",
            Reservation.scope_key.in_(sorted(limited_channels)),
            *(
                (Approval.campaign_v2_id != ignore_campaign_id,)
                if ignore_campaign_id is not None else ()
            ),
        ).all()
        for row in active:
            if type(row.reserved_messages) is not int or row.reserved_messages <= 0:
                uncertain.add(str(row.scope_key))
                continue
            reserved[str(row.scope_key)] += row.reserved_messages

    demand = defaultdict(int)
    for batch in plan.batches:
        if restricted_branch(batch.sucursal_canon, batch.provider_channel_id) and batch.provider_channel_id:
            demand[str(batch.provider_channel_id)] += len(batch.recipients)

    rows = []
    ready = held = 0
    for batch in plan.batches:
        channel = str(batch.provider_channel_id or "")
        count = len(batch.recipients)
        restricted = restricted_branch(batch.sucursal_canon, batch.provider_channel_id)
        reason = None
        if not channel:
            reason = "MISSING_CHANNEL"
        elif restricted and channel in uncertain:
            reason = "UNRESOLVED_PROVIDER_ACTIVITY"
        elif restricted and (
            demand[channel] + attempted[channel] + reserved[channel] >
            RESTRICTED_CHANNEL_LIMIT
        ):
            reason = "CHANNEL_EXCEPTION_250_EXCEEDED"
        if reason:
            held += count
        else:
            ready += count
        rows.append({
            "sucursal_canon": batch.sucursal_canon,
            "provider_channel_id": channel or None,
            "portfolio_key": None,
            "account_key": None,
            "phone_alias": None,
            "reset_timezone": "America/Tijuana",
            "reported_nominal_channel_limit": RESTRICTED_CHANNEL_LIMIT if restricted else None,
            "operator_channel_cap": RESTRICTED_CHANNEL_LIMIT if restricted else None,
            "operator_portfolio_cap": None,
            "policy_revision_id": None,
            "channel_evidence_id": None,
            "portfolio_evidence_id": None,
            "channel_remaining": None,
            "portfolio_remaining": None,
            "suite_channel_attempted": attempted[channel] if restricted else None,
            "suite_channel_reserved": reserved[channel] if restricted else None,
            "recipients": count,
            "recommendation": "REVIEW_HOLD" if reason else "CAPACITY_REVIEWED",
            "blocking_reason": reason,
            "restriction_kind": "CHANNEL_250_ROLLING_24H" if restricted else "NO_SUITE_DAILY_QUOTA",
        })
    return {
        "basis": BASIS,
        "status": "REVIEWABLE" if rows and not held else "INCOMPLETE",
        "send_authorized": False,
        "actual_meta_remaining": None,
        "coverage": "SUITE_RECORDED_ATTEMPTS_ONLY",
        "window_start": cutoff.isoformat(),
        "window_end": timestamp.isoformat(),
        "as_of": timestamp.isoformat(),
        "reviewed_recipients": ready,
        "hold_recommended_recipients": held,
        "batches": rows,
        "portfolio_demands": [],
    }
