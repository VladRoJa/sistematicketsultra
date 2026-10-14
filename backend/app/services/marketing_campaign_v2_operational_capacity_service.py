"""Issue 856: operator-set 24h Suite volume caps, NOT Meta remaining.

Only Suite-recorded provider attempts and active approvals are countable.
Provider messages generated outside Suite and Meta's actual remaining volume
are unknown. No source of "remaining messages" is inferred from nominal tier.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.marketing import (
    MarketingCampaignV2QuotaPolicyRevisionORM as Policy,
    MarketingCampaignV2CapacityReservationORM as Reservation,
    MarketingCampaignV2DispatchApprovalORM as Approval,
    MarketingCampaignV2ProviderCampaignORM as Child,
)

BASIS = "SUITE_OPERATOR_ROLLING_24H_V1"
WINDOW = timedelta(hours=24)
POSSIBLY_ATTEMPTED = frozenset({
    "SUBMITTING", "SUBMITTED", "SCHEDULED", "RECONCILIATION_REQUIRED",
    "PROVIDER_ERROR", "RETRY_ELIGIBLE", "RETRY_EXHAUSTED",
})
UNRESOLVED = frozenset({"SUBMITTING", "RECONCILIATION_REQUIRED"})


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _latest(rows: list[Any]) -> dict[str, Any]:
    # SQL is already newest first; defensive key uniqueness keeps deterministic policy identity.
    result = {}
    for row in rows:
        result.setdefault(str(row.provider_channel_id), row)
    return result


def _has_limits(row: Any) -> bool:
    return (getattr(row, "operational_channel_cap", None) is not None or
            getattr(row, "operational_portfolio_cap", None) is not None)


def assess_operational_capacity(
    *, plan: Any, session: Any, now: datetime,
    ignore_campaign_id: int | None = None, force: bool = False,
) -> dict | None:
    """None => legacy operator-attested contract; otherwise self-contained safe result.

    Every relevant channel/portfolio must have explicit positive, consistent
    operator caps. The 24-hour window rolls, regardless of nominal reset timezone.
    """
    timestamp = _utc(now)
    cutoff = timestamp - WINDOW
    channels = {str(b.provider_channel_id) for b in plan.batches if b.provider_channel_id}
    if not channels:
        return None if not force else _blocked_missing(plan, timestamp)
    selected_rows = session.query(Policy).filter(
        Policy.provider_channel_id.in_(sorted(channels)),
        Policy.valid_from <= timestamp,
    ).order_by(Policy.valid_from.desc(), Policy.id.desc()).all()
    selected = _latest(selected_rows)
    if not force and not any(_has_limits(p) for p in selected.values()):
        return None

    portfolios = {str(p.portfolio_key) for p in selected.values()}
    related_rows = session.query(Policy).filter(
        Policy.portfolio_key.in_(sorted(portfolios)),
        Policy.valid_from <= timestamp,
    ).order_by(Policy.valid_from.desc(), Policy.id.desc()).all() if portfolios else []
    related = _latest(related_rows)
    # For channel reassignment in the rolling window, include its previous
    # portfolio identity: fail closed instead of undercounting the old portfolio.
    unstable = set()
    for p in related_rows:
        newest = related.get(str(p.provider_channel_id))
        if (newest is not None and _utc(p.valid_from) >= cutoff and
                str(p.portfolio_key) != str(newest.portfolio_key)):
            unstable.add(str(newest.portfolio_key))

    channel_usage = defaultdict(int)
    portfolio_usage = defaultdict(int)
    channel_reserved = defaultdict(int)
    portfolio_reserved = defaultdict(int)
    unresolved_portfolios = set()
    if related:
        events = session.query(Child).filter(
            Child.provider == "IVENTAS",
            Child.provider_channel_id.in_(sorted(related)),
            Child.status.in_(sorted(POSSIBLY_ATTEMPTED)),
        ).all()
        for evt in events:
            if (ignore_campaign_id is not None and
                    int(evt.campaign_v2_id) == int(ignore_campaign_id)):
                continue
            if (evt.status == "PROVIDER_ERROR" and
                    evt.reconciliation_resolution == "NOT_CREATED_CONFIRMED"):
                continue
            mapped = related.get(str(evt.provider_channel_id))
            if mapped is None:
                continue
            attempt_at = evt.submit_started_at or evt.submitted_at or evt.created_at
            if attempt_at is None:
                unresolved_portfolios.add(str(mapped.portfolio_key))
                continue
            age = _utc(attempt_at)
            if age > timestamp or (evt.status in UNRESOLVED and age < cutoff):
                unresolved_portfolios.add(str(mapped.portfolio_key))
                continue
            if age < cutoff:
                continue
            if type(evt.recipient_count) is not int or evt.recipient_count <= 0:
                unresolved_portfolios.add(str(mapped.portfolio_key))
                continue
            channel_usage[str(evt.provider_channel_id)] += evt.recipient_count
            portfolio_usage[str(mapped.portfolio_key)] += evt.recipient_count

        active_reservations = session.query(Reservation).join(
            Approval, Approval.id == Reservation.approval_id,
        ).filter(
            Reservation.reserved_until > timestamp,
            *(
                (Approval.campaign_v2_id != ignore_campaign_id,)
                if ignore_campaign_id is not None else ()
            ),
        ).all()
        for reservation in active_reservations:
            scope = (reservation.scope_kind, reservation.scope_key)
            count = int(reservation.reserved_messages)
            if count <= 0:
                unresolved_portfolios.update(portfolios)
                continue
            if scope[0] == "CHANNEL" and scope[1] in related:
                channel_reserved[scope[1]] += count
            if scope[0] == "PORTFOLIO" and scope[1] in portfolios:
                portfolio_reserved[scope[1]] += count

    demand_channels = defaultdict(int)
    demand_portfolios = defaultdict(int)
    for batch in plan.batches:
        channel = str(batch.provider_channel_id or "")
        count = len(batch.recipients)
        demand_channels[channel] += count
        row = selected.get(channel)
        if row:
            demand_portfolios[str(row.portfolio_key)] += count

    portfolio_caps: dict[str, int] = {}
    inconsistent_portfolios = set()
    for row in related.values():
        key = str(row.portfolio_key)
        limit = getattr(row, "operational_portfolio_cap", None)
        channel_limit = getattr(row, "operational_channel_cap", None)
        if (type(limit) is not int or limit <= 0 or
                type(channel_limit) is not int or channel_limit <= 0):
            inconsistent_portfolios.add(key)
        elif key in portfolio_caps and portfolio_caps[key] != limit:
            inconsistent_portfolios.add(key)
        else:
            portfolio_caps[key] = limit

    rows = []
    reviewed = held = 0
    for batch in plan.batches:
        channel = str(batch.provider_channel_id or "")
        count = len(batch.recipients)
        row = selected.get(channel)
        portfolio = str(row.portfolio_key) if row else ""
        ccap = getattr(row, "operational_channel_cap", None) if row else None
        pcap = portfolio_caps.get(portfolio)
        reason = None
        if row is None:
            reason = "MISSING_QUOTA_POLICY"
        elif (type(ccap) is not int or ccap <= 0 or
              type(pcap) is not int or pcap <= 0):
            reason = "MISSING_OPERATOR_CAP"
        elif portfolio in inconsistent_portfolios or portfolio in unstable:
            reason = "SHARED_PORTFOLIO_POLICY_CONFLICT"
        elif portfolio in unresolved_portfolios:
            reason = "UNRESOLVED_PROVIDER_ACTIVITY"
        elif (getattr(row, "nominal_channel_limit", None) is not None and
              ccap > int(row.nominal_channel_limit)):
            reason = "OPERATOR_CAP_EXCEEDS_NOMINAL"
        elif (demand_channels[channel] + channel_usage[channel] +
              channel_reserved[channel] > ccap):
            reason = "CHANNEL_OPERATOR_LIMIT_EXCEEDED"
        elif (demand_portfolios[portfolio] + portfolio_usage[portfolio] +
              portfolio_reserved[portfolio] > pcap):
            reason = "PORTFOLIO_OPERATOR_LIMIT_EXCEEDED"
        if reason:
            held += count
        else:
            reviewed += count
        rows.append({
            "sucursal_canon": batch.sucursal_canon,
            "provider_channel_id": channel or None,
            "portfolio_key": portfolio or None,
            "account_key": row.account_key if row else None,
            "phone_alias": row.phone_alias if row else None,
            "reset_timezone": row.reset_timezone if row else None,
            "reported_nominal_channel_limit": row.nominal_channel_limit if row else None,
            "operator_channel_cap": ccap,
            "operator_portfolio_cap": pcap,
            "policy_revision_id": int(row.id) if row else None,
            "suite_channel_attempted": channel_usage[channel],
            "suite_portfolio_attempted": portfolio_usage[portfolio],
            "suite_channel_reserved": channel_reserved[channel],
            "suite_portfolio_reserved": portfolio_reserved[portfolio],
            "channel_remaining": None, "portfolio_remaining": None,
            "channel_evidence_id": None, "portfolio_evidence_id": None,
            "recipients": count,
            "recommendation": "REVIEW_HOLD" if reason else "CAPACITY_REVIEWED",
            "blocking_reason": reason,
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
        "reviewed_recipients": reviewed,
        "hold_recommended_recipients": held,
        "batches": rows,
        "portfolio_demands": [
            {
                "portfolio_key": key, "recipients": demand_portfolios[key],
                "operational_cap": portfolio_caps.get(key),
                "suite_attempted": portfolio_usage[key],
                "suite_reserved": portfolio_reserved[key],
                "attested_remaining": None,
            }
            for key in sorted(demand_portfolios)
        ],
    }


def _blocked_missing(plan: Any, timestamp: datetime) -> dict:
    rows = [{
        "sucursal_canon": b.sucursal_canon, "provider_channel_id": b.provider_channel_id,
        "portfolio_key": None, "channel_evidence_id": None,
        "portfolio_evidence_id": None, "policy_revision_id": None,
        "recipients": len(b.recipients),
        "recommendation": "REVIEW_HOLD",
        "blocking_reason": "MISSING_QUOTA_POLICY",
    } for b in plan.batches]
    return {
        "basis": BASIS, "status": "INCOMPLETE", "send_authorized": False,
        "actual_meta_remaining": None, "coverage": "SUITE_RECORDED_ATTEMPTS_ONLY",
        "as_of": timestamp.isoformat(), "reviewed_recipients": 0,
        "hold_recommended_recipients": sum(x["recipients"] for x in rows),
        "batches": rows, "portfolio_demands": [],
    }
