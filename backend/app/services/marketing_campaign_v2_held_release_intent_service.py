"""Issue #856 D3c1 — HELD release eligibility and immutable intent.

Never changes a HELD child, renews an old approval or reserves/sends quota.
The eventual derived campaign and its fresh independent approval are a
separate, fail-closed step. No recipient phone leaves this service.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2GovernedExecutionORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2HeldReleaseIntentORM,
    MarketingCampaignV2QuotaCapacityAttestationORM,
)
from app.services.marketing_campaign_v2_dispatch_approval_service import _database_date
from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
from app.services.marketing_campaign_v2_submit_service import (
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)
from app.services.marketing_campaign_v2_quota_service import assess_preflight_capacity
from app.services.marketing_campaign_v2_governed_dispatch_service import manifest_digest


class HeldReleaseValidation(ValueError):
    pass


class HeldReleaseConflict(RuntimeError):
    pass


class HeldReleaseNotFound(LookupError):
    pass


def _required_id(v: Any, label: str) -> int:
    if type(v) is not int or v <= 0:
        raise HeldReleaseValidation(label + " inválido.")
    return v


def _utc(now: datetime | None) -> datetime:
    value = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise HeldReleaseValidation("Se requiere fecha con zona horaria.")
    return value.astimezone(timezone.utc)


def _audit_text(v: Any, name: str, length: int) -> str:
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > length:
        raise HeldReleaseValidation(name + " es obligatorio.")
    return v.strip()


def _load_source(*, campaign_id: int, child_id: int, session: Any, lock: bool):
    q = session.query(MarketingCampaignV2ORM).filter(
        MarketingCampaignV2ORM.id == campaign_id,
    )
    campaign = (q.with_for_update() if lock else q).one_or_none()
    if campaign is None:
        raise HeldReleaseNotFound("Campaña de origen inexistente.")
    q = session.query(MarketingCampaignV2DispatchApprovalORM).filter(
        MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id,
    )
    approval = (q.with_for_update() if lock else q).one_or_none()
    if approval is None:
        raise HeldReleaseConflict("Campaña sin aprobación gobernada.")
    q = session.query(MarketingCampaignV2GovernedExecutionORM).filter(
        MarketingCampaignV2GovernedExecutionORM.approval_id == approval.id,
    )
    execution = (q.with_for_update() if lock else q).one_or_none()
    if execution is None or execution.status != "COMPLETE":
        raise HeldReleaseConflict(
            "La ejecución original no está COMPLETE; reconciliar/cerrar antes."
        )
    q = session.query(MarketingCampaignV2ProviderCampaignORM).filter(
        MarketingCampaignV2ProviderCampaignORM.id == child_id,
        MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id,
    )
    child = (q.with_for_update() if lock else q).one_or_none()
    if child is None:
        raise HeldReleaseNotFound("Child inexistente en la campaña de origen.")
    manifest = dict(approval.manifest_json or {})
    if manifest.get("version") != "D2B_READY_HELD_V1" or manifest.get("send_authorized") is not False:
        raise HeldReleaseConflict("El origen no tiene manifiesto D2B válido.")
    defined = {row.get("sucursal_canon"): row for row in manifest.get("batches", [])
               if isinstance(row, dict)}
    if len(defined) != len(manifest.get("batches", [])):
        raise HeldReleaseConflict("Manifiesto de origen duplicado.")
    specification = defined.get(child.sucursal_canon)
    if specification is None or specification.get("planned_status") != "HELD":
        raise HeldReleaseConflict("Solo se admite child HELD del manifiesto original.")
    if (child.status != "HELD" or child.hold_reason != "CHANNEL_DAILY_QUOTA" or
            child.provider_campaign_id is not None or child.submit_started_at is not None or
            child.submitted_at is not None or child.held_at is None or
            child.held_by_user_id is None or
            dict(child.hold_evidence_json or {}) != specification.get("hold_evidence") or
            child.dispatch_fingerprint != approval.dispatch_fingerprint):
        raise HeldReleaseConflict("HELD alterado o intentado; no se libera.")
    siblings = session.query(MarketingCampaignV2ProviderCampaignORM).filter(
        MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id,
    ).all()
    if len(siblings) != len(defined) or {s.sucursal_canon for s in siblings} != set(defined):
        raise HeldReleaseConflict("Children del origen incompletos o duplicados.")
    last_submitted = None
    for sibling in siblings:
        if sibling.sucursal_canon == child.sucursal_canon:
            continue
        prior_status = defined[sibling.sucursal_canon].get("planned_status")
        if prior_status == "READY":
            if (sibling.status != "SUBMITTED" or sibling.provider_campaign_id is None
                    or sibling.submitted_at is None):
                raise HeldReleaseConflict("Otro READY no está confirmado SUBMITTED.")
            submitted_at = _database_date(sibling.submitted_at)
            last_submitted = max(last_submitted, submitted_at) if last_submitted else submitted_at
        elif prior_status == "HELD":
            if (sibling.status != "HELD" or sibling.submit_started_at is not None or
                    sibling.provider_campaign_id is not None):
                raise HeldReleaseConflict("Otro HELD fue alterado.")
        else:
            raise HeldReleaseConflict("Estado de origen fuera de contrato.")
    return campaign, approval, execution, child, specification, last_submitted


def _evaluate(*, campaign_id: int, child_id: int, allowed_sucursal_keys: Any,
              session: Any, timestamp: datetime, lock: bool) -> dict:
    if session.get_bind().dialect.name != "postgresql":
        raise HeldReleaseConflict("La evaluación D3c requiere PostgreSQL.")
    _, approval, _, child, original, last_sent = _load_source(
        campaign_id=campaign_id, child_id=child_id, session=session, lock=lock,
    )
    plan = build_campaign_v2_preflight(
        campaign_id=campaign_id, template_id=int(approval.template_id),
        allowed_sucursal_keys=allowed_sucursal_keys, session=session, now=timestamp,
    )
    if not plan.ready or plan.mode != "IMMEDIATE":
        raise HeldReleaseConflict("Cohorte actual bloqueada; revisar filtros de exclusión.")
    batches = [b for b in plan.batches if b.sucursal_canon == child.sucursal_canon]
    if len(batches) != 1 or not batches[0].ready:
        raise HeldReleaseConflict("La sucursal HELD no coincide con el preflight.")
    batch = batches[0]
    if (batch.provider_channel_id != child.provider_channel_id or
            batch.channel_binding_id != child.channel_binding_id or
            len(batch.recipients) != int(child.recipient_count) or
            original.get("recipients") != len(batch.recipients)):
        raise HeldReleaseConflict("Cambió el canal, volumen o binding del HELD.")
    current_snapshot = serialize_campaign_v2_provider_request_snapshot(
        build_campaign_v2_provider_dispatch_batch(plan=plan, batch=batch),
    )
    if current_snapshot != dict(child.request_snapshot_json or {}):
        raise HeldReleaseConflict(
            "El snapshot congelado ya no coincide con el destinatario enviable actual."
        )
    capacity = assess_preflight_capacity(
        plan=replace(plan, batches=(batch,)), session=session, now=timestamp,
    )
    rows = capacity.get("batches") or []
    if (capacity.get("status") != "REVIEWABLE" or len(rows) != 1 or
            rows[0].get("recommendation") != "CAPACITY_REVIEWED" or
            rows[0].get("channel_evidence_id") is None or
            rows[0].get("portfolio_evidence_id") is None):
        raise HeldReleaseConflict("Sin cuota NUEVA vigente para canal y portafolio.")
    quota = rows[0]
    original_cutoff = max(
        [_database_date(approval.approved_at)]
        + ([last_sent] if last_sent is not None else []),
    )
    evidence = []
    for eid, kind, key in (
        (quota["channel_evidence_id"], "CHANNEL", child.provider_channel_id),
        (quota["portfolio_evidence_id"], "PORTFOLIO", quota["portfolio_key"]),
    ):
        row = session.get(MarketingCampaignV2QuotaCapacityAttestationORM, int(eid))
        if (row is None or row.scope_kind != kind or row.scope_key != key or
                _database_date(row.observed_at) <= original_cutoff or
                _database_date(row.observed_at) > timestamp or
                _database_date(row.expires_at) <= timestamp or
                _database_date(row.window_ends_at) <= timestamp):
            raise HeldReleaseConflict(
                "Atestación debe ser posterior al envío original y seguir vigente."
            )
        evidence.append({"scope_kind": kind, "scope_key": key,
                         "attestation_id": int(row.id),
                         "observed_at": _database_date(row.observed_at).isoformat(),
                         "expires_at": _database_date(row.expires_at).isoformat()})
    digest = manifest_digest(approval.manifest_json)
    payload = {
        "version": "D3C1_RELEASE_INTENT_V1",
        "source_campaign_id": campaign_id,
        "source_approval_id": int(approval.id),
        "source_child_id": child_id,
        "source_manifest_digest": digest,
        "original_snapshot_sha256": hashlib.sha256(json.dumps(
            current_snapshot, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest(),
        "preflight_fingerprint": plan.dispatch_fingerprint,
        "recipient_count": int(child.recipient_count),
        "fresh_evidence": evidence,
    }
    candidate_fingerprint = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return {
        "source_campaign_id": campaign_id, "source_approval_id": int(approval.id),
        "source_child_id": child_id, "sucursal_canon": child.sucursal_canon,
        "recipient_count": int(child.recipient_count),
        "source_manifest_digest": digest, "candidate_fingerprint": candidate_fingerprint,
        "evidence": evidence, "eligible_to_request": True,
        "status": "ELIGIBLE_FOR_INTENT_ONLY", "send_authorized": False,
        "quota_reserved": False, "held_released": False,
        "next_action": "CREATE_NEW_FROZEN_COHORT_AND_REPEAT_ALL_APPROVAL_GATES",
    }


def preview_held_release(*, campaign_id: int, child_id: int,
                         allowed_sucursal_keys: Any,
                         session: Any | None = None, now: datetime | None = None) -> dict:
    campaign_id, child_id = _required_id(campaign_id, "campaign_id"), _required_id(child_id, "child_id")
    active = session if session is not None else db.session
    return _evaluate(campaign_id=campaign_id, child_id=child_id,
                     allowed_sucursal_keys=allowed_sucursal_keys,
                     session=active, timestamp=_utc(now), lock=False)


def request_held_release_intent(
    *, campaign_id: int, child_id: int, expected_candidate_fingerprint: Any,
    expected_recipient_count: Any, source_reference: Any, reason: Any,
    actor_user_id: int, allowed_sucursal_keys: Any,
    session: Any | None = None, now: datetime | None = None,
) -> dict:
    campaign_id, child_id = _required_id(campaign_id, "campaign_id"), _required_id(child_id, "child_id")
    actor_user_id = _required_id(actor_user_id, "actor_user_id")
    expected_recipient_count = _required_id(expected_recipient_count, "expected_recipient_count")
    if (not isinstance(expected_candidate_fingerprint, str)
            or re.fullmatch("[0-9a-f]{64}", expected_candidate_fingerprint) is None):
        raise HeldReleaseValidation("Huella exacta de preview requerida.")
    source = _audit_text(source_reference, "source_reference", 255)
    reason = _audit_text(reason, "reason", 2000)
    active = session if session is not None else db.session
    try:
        # No quota reservation or mutation of parent, approval or child.
        # Locking the original campaign serializes competing operator requests.
        preview = _evaluate(
            campaign_id=campaign_id, child_id=child_id,
            allowed_sucursal_keys=allowed_sucursal_keys, session=active,
            timestamp=_utc(now), lock=True,
        )
        if (preview["candidate_fingerprint"] != expected_candidate_fingerprint or
                preview["recipient_count"] != expected_recipient_count):
            raise HeldReleaseConflict("Preview cambió; revisar antes de solicitar.")
        existing = active.query(MarketingCampaignV2HeldReleaseIntentORM.id).filter(
            MarketingCampaignV2HeldReleaseIntentORM.source_child_id == child_id,
        ).first()
        if existing is not None:
            raise HeldReleaseConflict("Ya existe intención de liberación para este child.")
        intent = MarketingCampaignV2HeldReleaseIntentORM(
            source_campaign_id=campaign_id,
            source_approval_id=preview["source_approval_id"],
            source_child_id=child_id,
            source_manifest_digest=preview["source_manifest_digest"],
            candidate_fingerprint=preview["candidate_fingerprint"],
            candidate_recipients=expected_recipient_count,
            evidence_json={"version": "D3C1_INTENT", "fresh_quota": preview["evidence"],
                           "send_authorized": False, "quota_reserved": False},
            source_reference=source, reason=reason, requested_by_user_id=actor_user_id,
            requested_at=_utc(now), status="PENDING_FRESH_COHORT",
        )
        active.add(intent)
        active.commit()
        return {
            "intent_id": int(intent.id), "source_campaign_id": campaign_id,
            "source_child_id": child_id, "candidate_fingerprint": expected_candidate_fingerprint,
            "status": "PENDING_FRESH_COHORT", "send_authorized": False,
            "held_released": False, "quota_reserved": False,
        }
    except (HeldReleaseConflict, HeldReleaseNotFound, HeldReleaseValidation):
        active.rollback()
        raise
    except IntegrityError as exc:
        active.rollback()
        raise HeldReleaseConflict("Solicitud concurrente duplicada.") from exc
    except SQLAlchemyError:
        active.rollback()
        raise
