"""Prepare one QA_MANUAL cohort per effective channel; never dispatch here.

All sending stays in D2a/D2b/D2c. Existing campaign/recipient/child records are
the durable ledger. The source campaign is read-only, not a recipient source.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign, MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2ProviderCampaignORM as Child,
    MarketingCampaignV2ChannelBindingORM as Binding,
    MarketingCampaignV2TemplateORM as Template,
    MarketingCampaignV2DispatchApprovalORM as Approval,
)
from app.services.marketing_phone import normalize_phone
from app.services.marketing_campaign_v2_qa_http_service import preview_qa_manual_http
from app.services.marketing_campaign_v2_qa_manual_service import freeze_campaign_v2_qa_manual
from app.services.marketing_campaign_v2_confirmed_rejection import confirmed_rejected_child
from app.services.marketing_campaign_v2_template_evidence_service import template_signature, EVIDENCE_VALID_FOR
from app.services.marketing_campaign_v2_dispatch_config_service import template_file_url

KEY = "template_probe_v1"


class TemplateProbeValidation(ValueError):
    pass


class TemplateProbeConflict(RuntimeError):
    pass


def _signature(template):
    return hashlib.sha256(json.dumps(
        [template_signature(template), template_file_url(template)],
        separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()


def _source(campaign_id, session):
    if type(campaign_id) is not int or campaign_id <= 0:
        raise TemplateProbeValidation("Campaña inválida.")
    row = session.get(Campaign, campaign_id)
    if row is None or row.source == "QA_MANUAL":
        raise TemplateProbeValidation("Selecciona una campaña comercial congelada.")
    return row


def _groups(plan, session):
    """Use the exact preflight output, including frozen sender routing."""
    groups = {}
    if not plan.batches or plan.blocked_missing_branch or plan.blocked_invalid_phone:
        raise TemplateProbeValidation("Resuelve las identidades de sucursal antes de probar.")
    for batch in plan.batches:
        binding = session.get(Binding, batch.channel_binding_id) if batch.channel_binding_id else None
        if (binding is None or binding.provider != "IVENTAS" or not binding.is_active
                or not binding.is_default or binding.provider_channel_id != batch.provider_channel_id):
            raise TemplateProbeValidation("Canal emisor ausente o modificado; repite el preflight.")
        group = groups.setdefault(str(batch.provider_channel_id), {
            "binding_id": int(binding.id), "sender_sucursal_id": int(binding.sucursal_id),
            "sender": str(binding.sucursal_canon), "origins": [],
        })
        if group["binding_id"] != binding.id:
            raise TemplateProbeValidation("Identidad de canal emisor ambigua.")
        group["origins"].append(batch.sucursal_canon)
    for group in groups.values():
        group["origins"] = sorted(set(group["origins"]))
    return dict(sorted(groups.items()))


def _context(campaign_id, template_id, session):
    from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
    source = _source(campaign_id, session)
    if type(template_id) is not int or template_id <= 0:
        raise TemplateProbeValidation("Plantilla inválida.")
    plan = build_campaign_v2_preflight(
        campaign_id=campaign_id, template_id=template_id,
        allowed_sucursal_keys=None, session=session,
    )
    template = session.get(Template, template_id)
    return source, template, _groups(plan, session)


def _name(source_id, template_id, channel):
    digest = hashlib.sha256(channel.encode()).hexdigest()
    return f"QA Plantilla {source_id}-{template_id}-{digest}"


def _existing(source_id, template_id, channel, session):
    rows = session.query(Campaign).filter_by(
        source="QA_MANUAL", name=_name(source_id, template_id, channel),
    ).all()
    if len(rows) > 1:
        raise TemplateProbeConflict("Prueba duplicada; requiere revisión.")
    return rows[0] if rows else None


def _no_commercial_phone(source_id, phone, session):
    if session.query(Recipient.id).filter(
        Recipient.campaign_id == source_id, Recipient.phone_mx10 == phone,
    ).first() is not None:
        raise TemplateProbeValidation("El teléfono de prueba pertenece a la campaña comercial.")


def prepare_template_probes(*, campaign_id, template_id, recipient_name, phone,
                            authorization_reference, confirmed_authorized,
                            actor_user_id, session=None):
    """Freeze only, atomic and idempotent across UI retries and workers."""
    active = session if session is not None else db.session
    if confirmed_authorized is not True:
        raise TemplateProbeValidation("Confirma autorización expresa del teléfono para pruebas.")
    if (not isinstance(authorization_reference, str)
            or not 8 <= len(authorization_reference.strip()) <= 255):
        raise TemplateProbeValidation("Indica referencia de autorización del teléfono (8–255 caracteres).")
    if not isinstance(recipient_name, str) or not 1 <= len(recipient_name.strip()) <= 255:
        raise TemplateProbeValidation("Indica nombre del destinatario de prueba.")
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise TemplateProbeValidation("Actor inválido.")
    normalized = normalize_phone(phone) if isinstance(phone, str) else None
    if normalized is None:
        raise TemplateProbeValidation("Teléfono de prueba inválido.")
    if active.get_bind().dialect.name != "postgresql":
        raise TemplateProbeConflict("La preparación idempotente requiere PostgreSQL.")
    try:
        # Freeze helper flushes without committing; retain this lock across ALL
        # channel cohorts, metadata and recipients, including crash recovery.
        active.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                       {"scope": f"template-probe:{campaign_id}:{template_id}"})
        source, template, groups = _context(campaign_id, template_id, active)
        _no_commercial_phone(campaign_id, normalized, active)
        for channel, group in groups.items():
            existing = _existing(campaign_id, template_id, channel, active)
            if existing:
                spec = (existing.audience_definition_json or {}).get("source_metadata", {}).get(KEY)
                if (not isinstance(spec, dict) or spec.get("phone_mx10") != normalized
                        or spec.get("source_campaign_id") != campaign_id
                        or spec.get("template_id") != template_id
                        or spec.get("channel_id") != channel):
                    raise TemplateProbeConflict("Ya existe una prueba para el par; no puede sustituirse.")
                continue
            args = dict(name=_name(campaign_id, template_id, channel), purpose=source.purpose,
                        sucursal_id=group["sender_sucursal_id"], provider_channel_id=channel,
                        recipients=[{"name": recipient_name.strip(), "phone": normalized}], session=active)
            preview = preview_qa_manual_http(**args)
            spec = dict(source_campaign_id=campaign_id, template_id=template_id,
                        template_signature=_signature(template), channel_id=channel,
                        **group, phone_mx10=normalized, authorized_by_user_id=actor_user_id,
                        authorization_reference=authorization_reference.strip(),
                        authorized_at=datetime.now(timezone.utc).isoformat())
            args.pop("provider_channel_id")
            freeze_campaign_v2_qa_manual(
                **args, expected_preview_fingerprint=preview["preview_fingerprint"],
                created_by_user_id=actor_user_id, source_metadata={KEY: spec}, commit=False,
            )
        active.commit()
    except Exception:
        active.rollback()
        raise
    return template_probe_matrix(campaign_id=campaign_id, template_id=template_id, session=active)


def probe_spec(campaign):
    if campaign is None:
        return None
    definition = getattr(campaign, "audience_definition_json", None)
    metadata = definition.get("source_metadata", {}) if isinstance(definition, dict) else {}
    return metadata.get(KEY) if isinstance(metadata, dict) else None


def validate_probe_preflight(*, campaign, template_id, session):
    """Pin template/media, recipient and the CURRENT effective source route."""
    spec = probe_spec(campaign)
    if spec is None:
        return
    if not isinstance(spec, dict) or campaign.source != "QA_MANUAL":
        raise TemplateProbeValidation("Trazabilidad de prueba inválida.")
    if template_id != spec.get("template_id"):
        raise TemplateProbeValidation("La prueba está vinculada a otra plantilla.")
    _, template, groups = _context(spec["source_campaign_id"], template_id, session)
    group = groups.get(spec.get("channel_id"))
    if (group is None or any(group[k] != spec.get(k) for k in group)
            or _signature(template) != spec.get("template_signature")):
        raise TemplateProbeValidation("Cambió plantilla o canal de origen; prueba bloqueada.")
    recipients = session.query(Recipient).filter_by(campaign_id=int(campaign.id)).all()
    if (len(recipients) != 1 or recipients[0].phone_mx10 != spec.get("phone_mx10")
            or not spec.get("authorization_reference") or not spec.get("authorized_by_user_id")):
        raise TemplateProbeValidation("Destinatario de prueba no autorizado o alterado.")
    _no_commercial_phone(spec["source_campaign_id"], spec["phone_mx10"], session)


def validate_probe_claim(*, campaign, child, session):
    spec = probe_spec(campaign)
    if spec is None:
        return
    validate_probe_preflight(campaign=campaign, template_id=int(child.template_id), session=session)
    if (child.provider_channel_id != spec["channel_id"] or child.recipient_count != 1
            or session.query(Approval.id).filter_by(campaign_v2_id=campaign.id).first() is None):
        raise TemplateProbeValidation("La prueba requiere aprobación y despacho gobernados del canal exacto.")
    # Includes same child on explicit legacy retry, as well as replacement
    # children after a confirmed rejection. No POST for this pair a second time.
    if any(row.submit_started_at is not None for row in session.query(Child).filter_by(
            campaign_v2_id=campaign.id).all()):
        raise TemplateProbeValidation("La prueba ya tuvo un intento; no admite reenvíos.")


def _result(child):
    if child is None or child.submit_started_at is None:
        return "PENDIENTE"
    if (child.status in {"SUBMITTED", "SCHEDULED"} and child.provider_campaign_id
            and child.submitted_at is not None):
        return "ACEPTADA POR IVENTAS"
    if confirmed_rejected_child(child):
        return "RECHAZADA"
    return "INCIERTA"


def accepted_probe_channels(*, campaign_id, template, outbound_bindings, session, now=None):
    """Read existing accepted QA attempts; never recurse into source preflight.

    Uses the existing evidence validity window, exact current sender identities,
    and immutable provider snapshots. Acceptance is not delivery or send consent.
    """
    timestamp = now or datetime.now(timezone.utc)
    required = {}
    for row in outbound_bindings:
        channel = row["provider_channel_id"]
        binding = session.get(Binding, row["channel_binding_id"]) if row["channel_binding_id"] else None
        if (not channel or binding is None or not binding.is_active or not binding.is_default
                or binding.provider != "IVENTAS" or str(binding.provider_channel_id) != channel):
            continue
        group = required.setdefault(channel, dict(binding_id=int(binding.id),
            sender_sucursal_id=int(binding.sucursal_id), sender=str(binding.sucursal_canon), origins=[]))
        group["origins"].append(row["sucursal_canon"])
    accepted = set()
    for channel, group in required.items():
        group["origins"] = sorted(set(group["origins"]))
        qa = _existing(campaign_id, int(template.id), channel, session)
        spec = probe_spec(qa)
        if (not isinstance(spec, dict) or spec.get("source_campaign_id") != campaign_id
                or spec.get("template_id") != template.id or spec.get("channel_id") != channel
                or spec.get("template_signature") != _signature(template)
                or any(spec.get(k) != group[k] for k in group)
                or not spec.get("authorization_reference") or not spec.get("authorized_by_user_id")):
            continue
        children = session.query(Child).filter_by(campaign_v2_id=qa.id).all()
        if len(children) != 1:
            continue
        child = children[0]
        if (_result(child) != "ACEPTADA POR IVENTAS" or child.template_id != template.id
                or child.provider_channel_id != channel or child.recipient_count != 1
                or not child.submitted_by_user_id
                or int(child.retry_attempt_count or 0) != 0 or child.retry_history_json):
            continue
        stamp = child.submitted_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)  # DB timestamps are UTC.
        if not stamp <= timestamp < stamp + EVIDENCE_VALID_FOR:
            continue
        snapshot = child.request_snapshot_json or {}
        leads = snapshot.get("leads") if isinstance(snapshot, dict) else None
        if (not isinstance(leads, list) or len(leads) != 1 or not isinstance(leads[0], dict)
                or snapshot.get("provider_channel_id") != channel
                or snapshot.get("provider") != "IVENTAS"
                or snapshot.get("template_name") != str(template.template_name)
                or snapshot.get("file_url") != template_file_url(template)
                or snapshot.get("send_at") is not None
                or normalize_phone(leads[0].get("phone")) != spec.get("phone_mx10")):
            continue
        try:
            _no_commercial_phone(campaign_id, spec["phone_mx10"], session)
        except TemplateProbeValidation:
            continue
        accepted.add(channel)
    return frozenset(accepted)


def template_probe_matrix(*, campaign_id, template_id, session=None):
    active = session if session is not None else db.session
    _, template, groups = _context(campaign_id, template_id, active)
    rows = []
    for channel, group in groups.items():
        qa = _existing(campaign_id, template_id, channel, active)
        children = active.query(Child).filter_by(campaign_v2_id=qa.id).all() if qa else []
        child = children[0] if len(children) == 1 else None
        spec = probe_spec(qa) if qa else None
        result = "INCIERTA" if len(children) > 1 else _result(child)
        stale = bool(qa and (not isinstance(spec, dict)
            or spec.get("template_signature") != _signature(template)
            or any(spec.get(k) != group[k] for k in group)))
        expires = None
        evidence_current = False
        if result == "ACEPTADA POR IVENTAS":
            stamp = child.submitted_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            expires = stamp + EVIDENCE_VALID_FOR
            evidence_current = not stale and stamp <= datetime.now(timezone.utc) < expires
        rows.append(dict(
            channel_id=channel, **group, qa_campaign_id=int(qa.id) if qa else None,
            result="INCIERTA" if stale else result,
            recorded_acceptance=result, stale=stale,
            evidence_current=evidence_current, evidence_expires_at=expires.isoformat() if expires else None,
            child_id=int(child.id) if child else None,
            provider_campaign_id=child.provider_campaign_id if child else None,
            error_code=child.error_code if child else None,
            attempted_at=child.submit_started_at.isoformat() if child and child.submit_started_at else None,
            actor_user_id=child.submitted_by_user_id if child else None,
            authorized_by_user_id=spec.get("authorized_by_user_id") if isinstance(spec, dict) else None,
            recipient_phone_masked="******" + spec["phone_mx10"][-4:] if isinstance(spec, dict) else None,
            delivery_status="NO VERIFICADA",
        ))
    return dict(campaign_id=campaign_id, template_id=template_id,
                template_name=str(template.template_name), rows=rows,
                sends_started=False, commercial_dispatch_authorized=False)
