"""Issue #856 D3a — strictly read-only governed dispatch supervision.

No provider client, DML, auto-retry, quota renewal, HELD release or status change.
Operator-entered quota attestations must never be portrayed as Meta capacity.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2CapacityReservationORM,
    MarketingCampaignV2GovernedExecutionORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2QuotaCapacityAttestationORM,
)
from app.services.marketing_campaign_v2_dispatch_approval_service import _database_date
from app.services.marketing_campaign_v2_governed_dispatch_service import manifest_digest

INFLIGHT_REVIEW_THRESHOLD = timedelta(minutes=5)
CHILD_PENDING = frozenset({"READY", "HELD"})
CHILD_ACCEPTED = frozenset({"SUBMITTED", "SCHEDULED"})


class GovernedMonitorNotFound(LookupError):
    pass


class GovernedMonitorValidation(ValueError):
    pass


def _now_utc(now: datetime | None) -> datetime:
    current = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise GovernedMonitorValidation("El monitoreo requiere fecha con zona horaria.")
    return current.astimezone(timezone.utc)


def _iso(value: Any) -> str | None:
    return _database_date(value).isoformat() if value is not None else None


def _classify(*, approval: Any, execution: Any, children: list,
              timestamp: datetime) -> tuple[str, str | None]:
    if execution is not None and execution.status == "IN_FLIGHT":
        claim = _database_date(execution.updated_at)
        if timestamp - claim >= INFLIGHT_REVIEW_THRESHOLD:
            return "IN_FLIGHT_STALE", "VERIFY_PROVIDER_OUTCOME_MANUALLY"
        return "IN_FLIGHT", "DO_NOT_RESEND"
    if execution is not None and execution.status == "REVIEW_REQUIRED":
        return "REVIEW_REQUIRED", "VERIFY_PROVIDER_OUTCOME_MANUALLY"
    if any(child.status in {"SUBMITTING", "RECONCILIATION_REQUIRED"}
           for child in children):
        return "RECONCILIATION_REQUIRED", "VERIFY_PROVIDER_OUTCOME_MANUALLY"
    if any(child.status in {"PROVIDER_ERROR", "RETRY_ELIGIBLE", "RETRY_EXHAUSTED"}
           for child in children):
        return "PROVIDER_ERROR", "REVIEW_BEFORE_ANY_NEW_APPROVAL"
    if execution is not None and execution.status == "COMPLETE":
        return "COMPLETE", None
    if approval is not None and _database_date(approval.expires_at) <= timestamp:
        return "APPROVAL_EXPIRED", "NEW_AUTHORIZATION_POLICY_REQUIRED"
    if execution is not None:
        return "AUTHORIZED_NOT_DISPATCHED", "MANUAL_NEXT_CHILD_ONLY"
    if children:
        return "PREPARED_NOT_DISPATCHED", "INDEPENDENT_AUTHORIZATION_REQUIRED"
    if approval is not None:
        return "RESERVED_NOT_PREPARED", "MATERIALIZE_BEFORE_EXPIRY"
    return "NO_GOVERNED_APPROVAL", None


def read_governed_dispatch_monitor(*, campaign_id: int, session: Any | None = None,
                                  now: datetime | None = None) -> dict[str, Any]:
    """Pure persisted-state projection; no side effects or external calls."""
    if type(campaign_id) is not int or campaign_id <= 0:
        raise GovernedMonitorValidation("campaign_id inválido.")
    timestamp = _now_utc(now)
    active = session if session is not None else db.session
    campaign = active.get(MarketingCampaignV2ORM, campaign_id)
    if campaign is None:
        raise GovernedMonitorNotFound("Campaña no encontrada.")

    approval = active.query(MarketingCampaignV2DispatchApprovalORM).filter(
        MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id,
    ).one_or_none()
    execution = None
    reservations = []
    if approval is not None:
        execution = active.query(MarketingCampaignV2GovernedExecutionORM).filter(
            MarketingCampaignV2GovernedExecutionORM.approval_id == approval.id,
        ).one_or_none()
        reservations = active.query(MarketingCampaignV2CapacityReservationORM).filter(
            MarketingCampaignV2CapacityReservationORM.approval_id == approval.id,
        ).order_by(MarketingCampaignV2CapacityReservationORM.scope_kind,
                   MarketingCampaignV2CapacityReservationORM.scope_key).all()

    children = active.query(MarketingCampaignV2ProviderCampaignORM).filter(
        MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id,
    ).order_by(MarketingCampaignV2ProviderCampaignORM.id).all()
    status, action = _classify(
        approval=approval, execution=execution, children=children, timestamp=timestamp,
    )
    counts = dict(Counter(str(child.status) for child in children))
    quota_rows = []
    for row in reservations:
        evidence = active.get(MarketingCampaignV2QuotaCapacityAttestationORM,
                              row.attestation_id)
        quota_rows.append({
            "scope_kind": row.scope_kind,
            "scope_key": row.scope_key,
            "reserved_messages": int(row.reserved_messages),
            "attestation_id": int(row.attestation_id),
            "attestation_expires_at": _iso(evidence.expires_at) if evidence else None,
            "reserved_until": _iso(row.reserved_until),
            "is_current": bool(
                evidence is not None and
                _database_date(evidence.expires_at) > timestamp and
                _database_date(evidence.window_ends_at) > timestamp and
                _database_date(row.reserved_until) > timestamp and
                _database_date(evidence.observed_at) <= timestamp
            ),
        })
    rows = []
    for child in children:
        child_status = str(child.status)
        rows.append({
            "child_id": int(child.id),
            "sucursal_canon": child.sucursal_canon,
            "provider_channel_id": child.provider_channel_id,
            "recipient_count": int(child.recipient_count),
            "status": child_status,
            "provider_campaign_id": child.provider_campaign_id,
            "idempotency_key": child.idempotency_key,
            "hold_reason": child.hold_reason,
            "held_at": _iso(child.held_at),
            "submit_started_at": _iso(child.submit_started_at),
            "submitted_at": _iso(child.submitted_at),
            "error_code": child.error_code,
            "support_ref": child.support_ref,
            "reconciliation_resolution": child.reconciliation_resolution,
            "reconciled_at": _iso(child.reconciled_at),
            "needs_manual_review": child_status in {
                "SUBMITTING", "RECONCILIATION_REQUIRED", "PROVIDER_ERROR",
                "RETRY_ELIGIBLE", "RETRY_EXHAUSTED",
            },
            "send_authorized": False,
        })
    return {
        "campaign_id": campaign_id,
        "as_of": timestamp.isoformat(),
        "basis": "PERSISTED_STATE_AND_OPERATOR_ATTESTATIONS_NOT_META_VERIFIED",
        "status": status,
        "next_manual_action": action,
        "send_authorized": False,
        "may_auto_retry": False,
        "may_auto_release_held": False,
        "approval": ({
            "id": int(approval.id),
            "approved_at": _iso(approval.approved_at),
            "expires_at": _iso(approval.expires_at),
            "expired": _database_date(approval.expires_at) <= timestamp,
            "dispatch_fingerprint": approval.dispatch_fingerprint,
            "manifest_digest": manifest_digest(approval.manifest_json),
        } if approval is not None else None),
        "execution": ({
            "id": int(execution.id),
            "status": execution.status,
            "last_child_id": execution.last_child_id,
            "confirmed_at": _iso(execution.confirmed_at),
            "updated_at": _iso(execution.updated_at),
            "expires_at": _iso(execution.expires_at),
        } if execution is not None else None),
        "quota": {
            "basis": "OPERATOR_ATTESTED_NOT_META_VERIFIED",
            "all_current": bool(quota_rows) and all(r["is_current"] for r in quota_rows),
            "reservations": quota_rows,
        },
        "children_count": len(children),
        "children_by_status": counts,
        "children": rows,
    }
