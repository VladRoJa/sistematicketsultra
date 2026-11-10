"""Prepare one QA_MANUAL cohort per effective channel; never dispatch here.

All sending stays in D2a/D2b/D2c. Existing campaign/recipient/child records are
the durable ledger. The source campaign is read-only, not a recipient source.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from types import SimpleNamespace

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
from app.services.marketing_campaign_v2_dispatch_config_service import template_file_url
from app.services.marketing_campaign_v2_commercial_template_certification_service import (
    commercial_certifications, last_confirmed_template_rejection,
)

KEY = "template_probe_v1"


class TemplateProbeValidation(ValueError):
    pass


class TemplateProbeConflict(RuntimeError):
    pass


def _signature(template):
    # Certification version is independent of the *list* of allowed channels.
    # Adding a new sender requires QA only for that sender; existing senders
    # retain their evidence when name, variables and media remain unchanged.
    return hashlib.sha256(json.dumps(
        [int(template.id), str(template.template_name), template.variables_json or {},
         template_file_url(template)],
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
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
    if campaign_id is None:
        return _catalog_context(template_id, session)
    source = _source(campaign_id, session)
    if type(template_id) is not int or template_id <= 0:
        raise TemplateProbeValidation("Plantilla inválida.")
    plan = build_campaign_v2_preflight(
        campaign_id=campaign_id, template_id=template_id,
        allowed_sucursal_keys=None, session=session,
    )
    template = session.get(Template, template_id)
    return source, template, _groups(plan, session)



def _catalog_context(template_id, session):
    """Catalog-level scope: active effective senders, without a commercial cohort."""
    if type(template_id) is not int or template_id <= 0:
        raise TemplateProbeValidation("Plantilla inválida.")
    template = session.get(Template, template_id)
    if template is None or template.provider != "IVENTAS" or not template.is_active:
        raise TemplateProbeValidation("Plantilla iVentas activa no encontrada.")
    selected = template.compatible_channel_ids_json or []
    if not isinstance(selected, list):
        raise TemplateProbeValidation("Compatibilidad de plantilla inválida.")
    channels = set(map(str, selected))
    bindings = (session.query(Binding)
                .filter(Binding.provider == "IVENTAS",
                        Binding.is_active.is_(True),
                        Binding.is_default.is_(True)).all())
    by_id = {int(b.id): b for b in bindings}
    groups = {}
    for origin in bindings:
        metadata = origin.metadata_json or {}
        via_id = metadata.get("dispatch_via_binding_id") if isinstance(metadata, dict) else None
        sender = by_id.get(via_id) if isinstance(via_id, int) else origin
        if sender is None:
            raise TemplateProbeValidation("El canal emisor enrutado ya no está activo.")
        channel = str(sender.provider_channel_id)
        if channels and channel not in channels:
            continue
        group = groups.setdefault(channel, dict(
            binding_id=int(sender.id), sender_sucursal_id=int(sender.sucursal_id),
            sender=str(sender.sucursal_canon), origins=[]))
        if group["binding_id"] != sender.id:
            raise TemplateProbeValidation("Canales iVentas duplicados o ambiguos.")
        group["origins"].append(str(origin.sucursal_canon))
    if not groups:
        raise TemplateProbeValidation("No hay canales emisores activos compatibles.")
    for group in groups.values():
        group["origins"] = sorted(set(group["origins"]))
    purposes = template.purposes_json or []
    purpose = purposes[0] if purposes else "UNCLASSIFIED"
    if purpose not in {"NEW_SALE", "REACTIVATION", "ACTIVE_MEMBERS", "UNCLASSIFIED"}:
        raise TemplateProbeValidation("Propósito QA de plantilla no admitido.")
    return SimpleNamespace(purpose=purpose), template, dict(sorted(groups.items()))


def _name_prefix(template_id, channel):
    # Deterministic namespace by local template and effective sender only.
    # A different campaign/source must never create a second QA for this pair.
    digest = hashlib.sha256(channel.encode()).hexdigest()[:16]
    return f"QA Plantilla {template_id}-{digest}-"


def _name(template_id, signature, channel):
    # A relevant template/media change creates a new certification version.
    return _name_prefix(template_id, channel) + signature


def _existing(template_id, signature, channel, session):
    rows = session.query(Campaign).filter_by(
        source="QA_MANUAL", name=_name(template_id, signature, channel),
    ).all()
    if len(rows) > 1:
        raise TemplateProbeConflict("Certificación QA duplicada; requiere revisión.")
    return rows[0] if rows else None


def _previous_version(template_id, channel, session):
    # For UI only: expose that the prior certification no longer applies.
    return (session.query(Campaign)
            .filter(Campaign.source == "QA_MANUAL",
                    Campaign.name.like(_name_prefix(template_id, channel) + "%"))
            .order_by(Campaign.id.desc()).first())


def _no_commercial_phone(source_id, phone, session):
    if session.query(Recipient.id).filter(
        Recipient.campaign_id == source_id, Recipient.phone_mx10 == phone,
    ).first() is not None:
        raise TemplateProbeValidation("El teléfono de prueba pertenece a la campaña comercial.")



def prepare_template_probes(*, campaign_id, template_id, recipient_name, phone,
                            authorization_reference, confirmed_authorized,
                            actor_user_id, session=None, selected_channel_ids=None):
    """Freeze QA only for missing template-version/sender pairs, atomically.

    Existing certifications are reused across commercial campaigns; neither
    changing a test phone nor preparing another campaign sends a second QA.
    """
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
    # Explicit selection is mandatory for catalog operations. Legacy direct
    # callers may still omit it; all browser callers send an explicit list.
    if selected_channel_ids is not None and (
        not isinstance(selected_channel_ids, list) or not selected_channel_ids
        or any(not isinstance(item, str) or not item.strip()
               for item in selected_channel_ids)
        or len(selected_channel_ids) != len(set(selected_channel_ids))
        or len(selected_channel_ids) > 100
    ):
        raise TemplateProbeValidation("Selecciona uno o más canales emisores válidos.")
    normalized = normalize_phone(phone) if isinstance(phone, str) else None
    if normalized is None:
        raise TemplateProbeValidation("Teléfono de prueba inválido.")
    if active.get_bind().dialect.name != "postgresql":
        raise TemplateProbeConflict("La preparación idempotente requiere PostgreSQL.")
    try:
        # Single lock for this template: serializes QA from any commercial
        # campaign or worker, even when the channel sets overlap only partly.
        active.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                       {"scope": f"template-certification:{template_id}"})
        source, template, groups = _context(campaign_id, template_id, active)
        if selected_channel_ids is not None:
            unknown = set(selected_channel_ids) - set(groups)
            if unknown:
                raise TemplateProbeValidation("La selección contiene canales ajenos a la plantilla.")
            groups = {channel: group for channel, group in groups.items()
                      if channel in set(selected_channel_ids)}
        signature = _signature(template)
        # A proven commercial delivery is already a certification; do not
        # generate duplicate QA cohorts for those exact channel/version pairs.
        delivered = commercial_certifications(
            template=template, groups=groups, signature=signature, session=active,
        )
        for channel, group in groups.items():
            # The existing QA belongs to the template version and sender,
            # never to the commercial campaign currently open.
            if channel in delivered or _existing(template_id, signature, channel, active):
                continue
            if campaign_id is not None:
                _no_commercial_phone(campaign_id, normalized, active)
            args = dict(name=_name(template_id, signature, channel), purpose=source.purpose,
                        sucursal_id=group["sender_sucursal_id"], provider_channel_id=channel,
                        recipients=[{"name": recipient_name.strip(), "phone": normalized}], session=active)
            preview = preview_qa_manual_http(**args)
            spec = dict(source_campaign_id=campaign_id, template_id=template_id,
                        template_signature=signature, channel_id=channel,
                        **group, phone_mx10=normalized, authorized_by_user_id=actor_user_id,
                        authorization_reference=authorization_reference.strip(),
                        authorized_at=datetime.now(timezone.utc).isoformat(),
                        certification_scope="TEMPLATE_VERSION_CHANNEL_V2")
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
    """Pin QA to its immutable template version, sender and test recipient.

    The commercial campaign originally used to discover this pair is NOT
    a dependency: other commercial campaigns may share the certification.
    """
    spec = probe_spec(campaign)
    if spec is None:
        return
    if not isinstance(spec, dict) or campaign.source != "QA_MANUAL":
        raise TemplateProbeValidation("Trazabilidad de prueba inválida.")
    if template_id != spec.get("template_id"):
        raise TemplateProbeValidation("La prueba está vinculada a otra plantilla.")
    template = session.get(Template, template_id)
    binding = session.get(Binding, spec.get("binding_id"))
    if (template is None or binding is None
            or int(binding.id) != spec.get("binding_id")
            or not binding.is_active or not binding.is_default
            or binding.provider != "IVENTAS"
            or str(binding.provider_channel_id) != spec.get("channel_id")
            or int(binding.sucursal_id) != spec.get("sender_sucursal_id")
            or str(binding.sucursal_canon) != spec.get("sender")
            or _signature(template) != spec.get("template_signature")):
        raise TemplateProbeValidation("Cambió la plantilla o el canal emisor; prueba bloqueada.")
    recipients = session.query(Recipient).filter_by(campaign_id=int(campaign.id)).all()
    if (len(recipients) != 1 or recipients[0].phone_mx10 != spec.get("phone_mx10")
            or not spec.get("authorization_reference") or not spec.get("authorized_by_user_id")):
        raise TemplateProbeValidation("Destinatario de prueba no autorizado o alterado.")


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
    """Reusable durable certification for the exact template-version/sender.

    A successful provider POST is evidence of acceptance, not delivery or
    permanent provider availability. No 24h expiry: that is only for the
    distinct manual-inventory attestation, not controlled QA certification.
    """
    timestamp = now or datetime.now(timezone.utc)
    signature = _signature(template)
    required = {}
    for row in outbound_bindings:
        channel = row["provider_channel_id"]
        binding = session.get(Binding, row["channel_binding_id"]) if row["channel_binding_id"] else None
        if (not channel or binding is None or not binding.is_active or not binding.is_default
                or binding.provider != "IVENTAS" or str(binding.provider_channel_id) != channel):
            continue
        required[channel] = dict(binding_id=int(binding.id),
            sender_sucursal_id=int(binding.sucursal_id), sender=str(binding.sucursal_canon))
    accepted = set()
    for channel, group in required.items():
        qa = _existing(int(template.id), signature, channel, session)
        spec = probe_spec(qa)
        if (not isinstance(spec, dict)
                or spec.get("certification_scope") != "TEMPLATE_VERSION_CHANNEL_V2"
                or spec.get("template_id") != template.id or spec.get("channel_id") != channel
                or spec.get("template_signature") != signature
                or any(spec.get(k) != value for k, value in group.items())
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
            stamp = stamp.replace(tzinfo=timezone.utc)
        if stamp > timestamp:
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
        # A subsequent deterministic TEMPLATE_NOT_FOUND invalidates prior
        # successful proof (QA or commercial) for this channel.
        if last_confirmed_template_rejection(
            template_id=int(template.id), channel=channel,
            session=session, after=child.submitted_at,
        ) is not None:
            continue
        accepted.add(channel)
    commercial = commercial_certifications(
        template=template, groups=required, signature=signature,
        session=session, now=timestamp,
    )
    return frozenset(accepted | set(commercial))



def template_probe_matrix(*, campaign_id, template_id, session=None):
    active = session if session is not None else db.session
    _, template, groups = _context(campaign_id, template_id, active)
    signature = _signature(template)
    outbound = [dict(provider_channel_id=channel, channel_binding_id=group["binding_id"])
                for channel, group in groups.items()]
    commercial = commercial_certifications(
        template=template, groups=groups, signature=signature, session=active,
    )
    certified = accepted_probe_channels(
        campaign_id=campaign_id, template=template,
        outbound_bindings=outbound, session=active,
    )
    rows = []
    for channel, group in groups.items():
        qa = _existing(template_id, signature, channel, active)
        historical = _previous_version(template_id, channel, active) if qa is None else None
        current_qa = qa is not None
        visible_qa = qa or historical
        children = active.query(Child).filter_by(campaign_v2_id=visible_qa.id).all() if visible_qa else []
        child = children[0] if len(children) == 1 else None
        spec = probe_spec(visible_qa) if visible_qa else None
        raw = _result(child) if len(children) <= 1 else "INCIERTA"
        stale = bool(historical or (qa and (not isinstance(spec, dict)
            or spec.get("template_signature") != signature
            or any(spec.get(k) != group[k] for k in ("binding_id", "sender_sucursal_id", "sender")))))
        rejection = last_confirmed_template_rejection(
            template_id=int(template.id), channel=channel, session=active,
        )
        if stale:
            status = "INVALIDADA"
        elif channel in certified:
            status = "VALIDADA"
        elif raw == "ACEPTADA POR IVENTAS":
            status = "INCIERTA"  # Persisted acceptance lacks valid current proof.
        elif rejection is not None and qa is None:
            status = "RECHAZADA"
        else:
            status = raw
        commercial_proof = commercial.get(channel) if channel in certified else None
        source = ("COMMERCIAL_DELIVERY" if commercial_proof else
                  "QA_MANUAL" if channel in certified else None)
        rows.append(dict(
            channel_id=channel, **group, qa_campaign_id=int(visible_qa.id) if visible_qa else None,
            result=status, recorded_acceptance=raw, stale=stale,
            evidence_current=channel in certified, evidence_expires_at=None,
            certification_source=source,
            certification_campaign_id=(
                commercial_proof["campaign_id"] if commercial_proof else None
            ),
            certification_snapshot_id=(
                commercial_proof["snapshot_id"] if commercial_proof else None
            ),
            certification_observed_at=(
                commercial_proof["observed_at"] if commercial_proof else None
            ),
            child_id=(commercial_proof["child_id"] if commercial_proof else
                      int(child.id) if child else
                      int(rejection.id) if rejection and status == "RECHAZADA" else None),
            provider_campaign_id=(
                commercial_proof["provider_campaign_id"] if commercial_proof else
                child.provider_campaign_id if child else None
            ),
            rejection_source=(
                "COMMERCIAL_REJECTION"
                if rejection is not None and qa is None and status == "RECHAZADA"
                else None
            ),
            rejection_campaign_id=(
                int(rejection.campaign_v2_id)
                if rejection is not None and qa is None and status == "RECHAZADA"
                else None
            ),
            error_code=(child.error_code if child else
                        rejection.error_code if rejection and status == "RECHAZADA" else None),
            attempted_at=(commercial_proof["submitted_at"] if commercial_proof else
                          child.submit_started_at.isoformat() if child and child.submit_started_at else None),
            actor_user_id=(commercial_proof["actor_user_id"] if commercial_proof else
                           child.submitted_by_user_id if child else None),
            authorized_by_user_id=spec.get("authorized_by_user_id") if isinstance(spec, dict) else None,
            recipient_phone_masked="******" + spec["phone_mx10"][-4:]
                if isinstance(spec, dict) and isinstance(spec.get("phone_mx10"), str) else None,
            delivery_status=(
                commercial_proof["delivery_status"] if commercial_proof
                else "NO VERIFICADA"
            ),
        ))
    return dict(campaign_id=campaign_id or 0, template_id=template_id,
                template_name=str(template.template_name), rows=rows,
                sends_started=False, commercial_dispatch_authorized=False)
