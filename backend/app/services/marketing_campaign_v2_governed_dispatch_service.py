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
from app.services.marketing_campaign_v2_contact_gate_service import (
    CampaignV2ContactGateConflict,
    acquire_campaign_v2_contact_gate,
    verify_outbound_contact_admission,
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
                   allowed_sucursal_keys: Any, ignore_self: bool,
                   refresh_after_lock: bool = True):
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
    # Never trust a timestamp captured before an advisory lock wait.
    effective_now = _utc(None) if refresh_after_lock else now
    if _database_date(approval.expires_at) <= effective_now:
        raise GovernedDispatchConflict("Autorización caducó durante revisión.")
    refreshed = build_campaign_v2_preflight(
        campaign_id=campaign_id, template_id=int(approval.template_id),
        allowed_sucursal_keys=allowed_sucursal_keys, session=session,
        now=effective_now,
    )
    refreshed_budget = estimate_preflight_cost(
        plan=refreshed, session=session, now=effective_now,
    )
    refreshed_manifest = _assert_manifest(refreshed, refreshed_budget, approval)
    if (refreshed.dispatch_fingerprint != plan.dispatch_fingerprint or
            refreshed_budget["quote_fingerprint"] != budget["quote_fingerprint"]):
        raise GovernedDispatchConflict("Plan o tarifa cambió durante el bloqueo.")
    plan = refreshed
    manifest = refreshed_manifest
    original_ready = tuple(
        batch for batch in plan.batches
        if manifest[batch.sucursal_canon]["planned_status"] == "READY"
    )
    scopes_plan = replace(plan, batches=original_ready)
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
                    row.submitted_at is not None or
                    row.provider_campaign_id is not None):
                raise GovernedDispatchConflict("HELD modificado o intentado.")
        elif row.status not in {"READY", "SUBMITTED"}:
            raise GovernedDispatchConflict("Un child requiere revisión manual previa.")
        elif row.status == "SUBMITTED":
            if not row.provider_campaign_id or row.submitted_at is None:
                raise GovernedDispatchConflict("SUBMITTED carece de identidad provider.")
        elif (row.submit_started_at is not None or row.provider_campaign_id is not None or
              row.submitted_at is not None or row.hold_reason is not None or
              row.held_at is not None or row.held_by_user_id is not None or
              bool(row.hold_evidence_json or {})):
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
            refresh_after_lock=now is None,
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


def execute_governed_child(
    *, campaign_id: int, execution_id: int, child_id: int,
    expected_digest: str, actor_user_id: int, provider: Any,
    send_enabled: bool, governed_enabled: bool,
    allowed_sucursal_keys: Any, session: Any | None = None,
    now: datetime | None = None,
) -> dict:
    """Dispatch exactly the next READY child. Never auto-resume failed attempts."""
    if send_enabled is not True or governed_enabled is not True:
        raise GovernedDispatchDisabled("Kill switch o gate D2c deshabilitado.")
    if any(type(x) is not int or x <= 0
           for x in (campaign_id, execution_id, child_id, actor_user_id)):
        raise GovernedDispatchConflict("Identidad de despacho inválida.")
    active = session if session is not None else db.session
    timestamp = _utc(now)
    try:
        # Hold the same gate as derived-cohort freeze and legacy claim paths.
        # Lock order: contact gate -> campaign -> approval -> execution -> child.
        acquire_campaign_v2_contact_gate(active)
        approval, plan, manifest, children, digest = _locked_review(
            campaign_id=campaign_id, session=active, now=timestamp,
            allowed_sucursal_keys=allowed_sucursal_keys, ignore_self=True,
            refresh_after_lock=now is None,
        )
        execution = active.query(MarketingCampaignV2GovernedExecutionORM).filter(
            MarketingCampaignV2GovernedExecutionORM.id == execution_id,
            MarketingCampaignV2GovernedExecutionORM.approval_id == approval.id,
        ).with_for_update().one_or_none()
        # The campaign/portfolio locks may have been held for minutes.
        # Never compare execution expiry with the earlier request timestamp.
        claim_time = _utc(None) if now is None else timestamp
        if (execution is None or execution.status != "AUTHORIZED" or
                digest != execution.manifest_digest or digest != expected_digest or
                _database_date(execution.expires_at) <= claim_time):
            raise GovernedDispatchConflict("Autorización de despacho inexistente, usada o vencida.")
        _check_child_identities(plan=plan, manifest=manifest, children=children)
        by_branch = {r.sucursal_canon: r for r in children}
        original_ready = [b for b in plan.batches
                          if manifest[b.sucursal_canon]["planned_status"] == "READY"]
        pending = [b for b in original_ready if by_branch[b.sucursal_canon].status == "READY"]
        if not pending:
            raise GovernedDispatchConflict("No existen children READY autorizables.")
        # A prior accepted child must be immutable. Other states are blocked
        # by _check_child_identities. No out-of-order or parallel sends.
        # An already accepted prefix must match the one durable execution
        # history. A foreign/manual SUBMITTED row cannot authorize the suffix.
        statuses = [by_branch[b.sucursal_canon].status for b in original_ready]
        if statuses != ["SUBMITTED"] * statuses.count("SUBMITTED") + (
                ["READY"] * statuses.count("READY")):
            raise GovernedDispatchConflict("Orden de envíos previo inconsistente.")
        submitted = [by_branch[b.sucursal_canon] for b in original_ready
                     if by_branch[b.sucursal_canon].status == "SUBMITTED"]
        prior_id = int(submitted[-1].id) if submitted else None
        if execution.last_child_id != prior_id:
            raise GovernedDispatchConflict("Historial de ejecución incompatible.")
        first_pending = pending[0]
        row = by_branch[first_pending.sucursal_canon]
        if int(row.id) != child_id:
            raise GovernedDispatchConflict("Solo se permite el siguiente READY en orden.")
        if any(by_branch[b.sucursal_canon].status != "SUBMITTED"
               for b in original_ready
               if b.sucursal_canon != first_pending.sucursal_canon
               and b not in pending):
            raise GovernedDispatchConflict("El historial anterior requiere revisión.")

        dispatch = build_campaign_v2_provider_dispatch_batch(
            plan=plan, batch=first_pending,
        )
        # Re-read provider snapshot under the shared lock immediately before
        # durable claim. A stale preflight is never sufficient for acceptance.
        verify_outbound_contact_admission(child=row, session=active)
        # Both claims are committed together, before any HTTP to the provider.
        # If the process crashes after commit, IN_FLIGHT blocks all replays.
        row.status = "SUBMITTING"
        row.submit_started_at = claim_time
        row.submitted_by_user_id = actor_user_id
        row.updated_at = claim_time
        row.error_code = None
        row.support_ref = None
        execution.status = "IN_FLIGHT"
        execution.last_child_id = child_id
        execution.updated_at = claim_time
        active.commit()
    except CampaignV2ContactGateConflict as exc:
        active.rollback()
        raise GovernedDispatchConflict(str(exc)) from exc
    except (GovernedDispatchConflict, SQLAlchemyError):
        active.rollback()
        raise

    # This part is reached only after durable authorization + child claim.
    try:
        outcome = provider.create_campaign(dispatch)
    except CampaignProviderDeterministicError as exc:
        result_status, code, http, ref = "PROVIDER_ERROR", exc.code, exc.http_status, exc.support_ref
    except CampaignProviderAmbiguousError as exc:
        result_status, code, http, ref = "RECONCILIATION_REQUIRED", exc.code, exc.http_status, exc.support_ref
    except CampaignProviderConfigurationError:
        result_status, code, http, ref = "PROVIDER_ERROR", "PROVIDER_CONFIGURATION", None, None
    except Exception:
        # Any unexpected exception may mean that the provider accepted HTTP.
        result_status, code, http, ref = "RECONCILIATION_REQUIRED", "UNEXPECTED_PROVIDER_RESULT", None, None
    else:
        result_status, code, http, ref = "SUBMITTED", None, outcome.http_status, None

    if result_status == "SUBMITTED":
        _persist_provider_success(
            row_id=child_id, provider_campaign_id=outcome.provider_campaign_id,
            deduplicated=outcome.deduplicated,
            response_metadata=outcome.response_metadata,
            accepted_status="SUBMITTED", actor_user_id=actor_user_id,
            session=active, now=_utc(None),
        )
    else:
        _persist_provider_failure(
            row_id=child_id, status=result_status, error_code=code,
            support_ref=ref, http_status=http,
            actor_user_id=actor_user_id, session=active, now=_utc(None),
        )

    # A failure stops the entire execution; no automatic retry or continuation.
    # On crash in this block, persisted IN_FLIGHT still blocks further calls.
    execution = active.get(MarketingCampaignV2GovernedExecutionORM, execution_id)
    if execution is None or execution.status != "IN_FLIGHT" or execution.last_child_id != child_id:
        raise GovernedDispatchConflict("Resultado persistido; ejecución requiere revisión.")
    execution.status = (
        "AUTHORIZED" if result_status == "SUBMITTED" and len(pending) > 1
        else "COMPLETE" if result_status == "SUBMITTED"
        else "REVIEW_REQUIRED"
    )
    execution.updated_at = _utc(None)
    active.commit()
    return {
        "execution_id": execution_id, "campaign_id": campaign_id,
        "child_id": child_id, "status": result_status,
        "execution_status": execution.status,
        "provider_campaign_id": (
            outcome.provider_campaign_id if result_status == "SUBMITTED" else None
        ),
        "error_code": code,
        "next_child_requires_fresh_validation": True,
    }
