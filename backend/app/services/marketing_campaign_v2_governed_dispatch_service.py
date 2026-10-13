"""D2c: persisted operator gate for one governed provider child per request.

Fail-closed: authorizing does not send. Dispatch requires two kill switches,
the exact authorization and child identity, fresh operator quota evidence,
and a durable READY->SUBMITTING claim. No implicit resume or retry.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2CapacityReservationORM,
    MarketingCampaignV2GovernedExecutionORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.services.marketing_campaign_v2_budget_service import estimate_preflight_cost
from app.services.marketing_campaign_v2_dispatch_approval_service import (
    _assess_scopes, _database_date,
)
from app.services.marketing_campaign_v2_manifest_service import (
    _assert_manifest, _validate_existing,
)
from app.services.marketing_campaign_v2_preflight_service import (
    build_campaign_v2_preflight, build_provider_campaign_idempotency_key,
)
from app.services.marketing_campaign_v2_submit_service import (
    _load_campaign_rows,
    _persist_provider_failure, _persist_provider_success,
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)
from app.services.marketing_campaign_v2_provider import (
    CampaignProviderAmbiguousError, CampaignProviderConfigurationError,
    CampaignProviderDeterministicError,
)


class GovernedDispatchConflict(RuntimeError):
    pass


class GovernedDispatchDisabled(RuntimeError):
    pass


def _utc(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise GovernedDispatchConflict("Se requiere timestamp con zona.")
    return now.astimezone(timezone.utc)


def manifest_digest(manifest: Any) -> str:
    return hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _locked_review(*, campaign_id: int, session: Any, now: datetime,
                   allowed_sucursal_keys: Any, ignore_self: bool):
    if session.get_bind().dialect.name != "postgresql":
        raise GovernedDispatchConflict("Despacho gobernado requiere PostgreSQL.")
    campaign = session.query(MarketingCampaignV2ORM).filter(
        MarketingCampaignV2ORM.id == campaign_id,
    ).with_for_update().one_or_none()
    approval = session.query(MarketingCampaignV2DispatchApprovalORM).filter(
        MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id,
    ).with_for_update().one_or_none()
    if campaign is None or approval is None or _database_date(approval.expires_at) <= now:
        raise GovernedDispatchConflict("Campaña o aprobación inexistente/vencida.")
    plan = build_campaign_v2_preflight(
        campaign_id=campaign_id, template_id=int(approval.template_id),
        allowed_sucursal_keys=allowed_sucursal_keys, session=session, now=now,
    )
    budget = estimate_preflight_cost(plan=plan, session=session, now=now)
    manifest = _assert_manifest(plan, budget, approval)
    original_ready = tuple(
        batch for batch in plan.batches
        if manifest[batch.sucursal_canon]["planned_status"] == "READY"
    )
    scopes_plan = replace(plan, batches=original_ready)
    _, scopes_before, _, _ = _assess_scopes(
        scopes_plan, session=session, timestamp=now,
        ignore_campaign_id=campaign_id if ignore_self else None,
    )
    for kind, key in sorted(scopes_before):
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": "mkt_v2_quota:" + kind + ":" + key},
        )
    # Caller supplies fresh now after lock in normal flow. The clock here
    # is refreshed even when the transaction waited for another operator.
    effective_now = datetime.now(timezone.utc) if now is None else now
    if _database_date(approval.expires_at) <= effective_now:
        raise GovernedDispatchConflict("Autorización caducó durante revisión.")
    _, scopes, evidence_ids, quota_rows = _assess_scopes(
        scopes_plan, session=session, timestamp=effective_now,
        ignore_campaign_id=campaign_id if ignore_self else None,
    )
    if dict(scopes_before) != dict(scopes):
        raise GovernedDispatchConflict("Cuota cambió durante bloqueo.")
    reservations = session.query(MarketingCampaignV2CapacityReservationORM).filter(
        MarketingCampaignV2CapacityReservationORM.approval_id == approval.id,
    ).all()
    by_scope = {(r.scope_kind, r.scope_key): r for r in reservations}
    if len(reservations) != len(by_scope) or set(by_scope) != set(scopes):
        raise GovernedDispatchConflict("Reservas incompletas.")
    for scope, count in scopes.items():
        row = by_scope[scope]
        if (int(row.reserved_messages) != int(count) or
                int(row.attestation_id) != int(evidence_ids[scope]) or
                _database_date(row.reserved_until) <= effective_now):
            raise GovernedDispatchConflict("Reserva de cuota incompatible o vencida.")
    for batch in original_ready:
        expected = manifest[batch.sucursal_canon]
        current = quota_rows[batch.sucursal_canon]
        if (expected["channel_attestation_id"] != current["channel_evidence_id"] or
                expected["portfolio_attestation_id"] != current["portfolio_evidence_id"] or
                expected["portfolio_key"] != current["portfolio_key"]):
            raise GovernedDispatchConflict("Cambió la evidencia aprobada por lote.")
    children = _load_campaign_rows(campaign_id=campaign_id, session=session)
    return approval, plan, manifest, children, manifest_digest(approval.manifest_json)


def _check_child_identities(*, plan: Any, manifest: dict, children: list):
    batches = {b.sucursal_canon: b for b in plan.batches}
    if len(children) != len(batches) or {c.sucursal_canon for c in children} != set(batches):
        raise GovernedDispatchConflict("Children incompletos o duplicados.")
    for row in children:
        batch = batches[row.sucursal_canon]
        definition = manifest[row.sucursal_canon]
        expected = build_provider_campaign_idempotency_key(
            campaign_v2_id=plan.campaign_id, batch=batch,
            dispatch_fingerprint=plan.dispatch_fingerprint,
        )
        snapshot = serialize_campaign_v2_provider_request_snapshot(
            build_campaign_v2_provider_dispatch_batch(plan=plan, batch=batch),
        )
        if (row.campaign_v2_id != plan.campaign_id or row.provider != plan.provider or
                row.sucursal_id != batch.sucursal_id or
                row.channel_binding_id != batch.channel_binding_id or
                row.provider_channel_id != batch.provider_channel_id or
                row.template_id != batch.template_id or
                row.template_name != batch.template_name or
                row.dispatch_fingerprint != plan.dispatch_fingerprint or
                row.idempotency_key != expected or
                int(row.recipient_count) != len(batch.recipients) or
                dict(row.request_snapshot_json or {}) != snapshot):
            raise GovernedDispatchConflict("Identidad o snapshot del child cambió.")
        if definition["planned_status"] == "HELD":
            if (row.status != "HELD" or
                    row.hold_reason != "CHANNEL_DAILY_QUOTA" or
                    dict(row.hold_evidence_json or {}) != definition["hold_evidence"] or
                    row.held_at is None or row.held_by_user_id is None or
                    row.submit_started_at is not None or
                    row.provider_campaign_id is not None):
                raise GovernedDispatchConflict("HELD modificado o intentado.")
        elif row.status not in {"READY", "SUBMITTED"}:
            raise GovernedDispatchConflict("Un child requiere revisión manual previa.")
        elif row.status == "SUBMITTED":
            if not row.provider_campaign_id or row.submitted_at is None:
                raise GovernedDispatchConflict("SUBMITTED carece de identidad provider.")
        elif (row.submit_started_at is not None or row.provider_campaign_id is not None or
              row.submitted_at is not None or row.hold_reason is not None):
            raise GovernedDispatchConflict("READY modificado o intentado.")


def authorize_governed_dispatch(
    *, campaign_id: int, approval_id: int, expected_digest: str,
    expected_ready_recipients: int, confirmed: bool, actor_user_id: int,
    allowed_sucursal_keys: Any, session: Any | None = None,
    now: datetime | None = None,
) -> dict:
    if (type(campaign_id) is not int or campaign_id <= 0 or
            type(approval_id) is not int or approval_id <= 0 or
            type(actor_user_id) is not int or actor_user_id <= 0 or
            type(expected_ready_recipients) is not int or
            expected_ready_recipients <= 0 or confirmed is not True or
            not isinstance(expected_digest, str) or len(expected_digest) != 64):
        raise GovernedDispatchConflict("Confirmación independiente inválida.")
    active = session if session is not None else db.session
    try:
        timestamp = _utc(now)
        approval, plan, manifest, children, digest = _locked_review(
            campaign_id=campaign_id, session=active, now=timestamp,
            allowed_sucursal_keys=allowed_sucursal_keys, ignore_self=False,
        )
        ready_count = sum(len(b.recipients) for b in plan.batches
                          if manifest[b.sucursal_canon]["planned_status"] == "READY")
        if (approval.id != approval_id or digest != expected_digest or
                ready_count != expected_ready_recipients):
            raise GovernedDispatchConflict("Confirmación difiere del manifiesto vigente.")
        _validate_existing(plan, manifest, children)
        if active.query(MarketingCampaignV2GovernedExecutionORM.id).filter(
            MarketingCampaignV2GovernedExecutionORM.approval_id == approval.id
        ).first() is not None:
            raise GovernedDispatchConflict("Esta aprobación ya tiene ejecución registrada.")
        execution = MarketingCampaignV2GovernedExecutionORM(
            approval_id=approval.id, manifest_digest=digest,
            confirmed_by_user_id=actor_user_id, confirmed_at=timestamp,
            expires_at=approval.expires_at, status="AUTHORIZED",
            updated_at=timestamp,
        )
        active.add(execution)
        active.commit()
        return {
            "execution_id": int(execution.id),
            "approval_id": int(approval.id),
            "campaign_id": campaign_id,
            "manifest_digest": digest,
            "ready_recipients": ready_count,
            "status": "AUTHORIZED",
            "provider_calls": 0,
        }
    except (GovernedDispatchConflict, IntegrityError, SQLAlchemyError):
        active.rollback()
        raise


def review_execution(*, campaign_id: int, session: Any | None = None) -> dict:
    active = session if session is not None else db.session
    approval = active.query(MarketingCampaignV2DispatchApprovalORM).filter(
        MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id
    ).one_or_none()
    if approval is None:
        return {"approval": None, "execution": None, "send_authorized": False}
    execution = active.query(MarketingCampaignV2GovernedExecutionORM).filter(
        MarketingCampaignV2GovernedExecutionORM.approval_id == approval.id,
    ).one_or_none()
    return {
        "approval_id": int(approval.id),
        "manifest_digest": manifest_digest(approval.manifest_json),
        "manifest": approval.manifest_json,
        "execution": ({
            "execution_id": int(execution.id), "status": execution.status,
            "last_child_id": execution.last_child_id,
        } if execution else None),
        "expires_at": _database_date(approval.expires_at).isoformat(),
        "send_authorized": False,
    }
