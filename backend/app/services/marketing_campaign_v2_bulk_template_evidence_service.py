"""Bulk read-only inventory review and audited reusable iVentas template proof.

No provider HTTP, no send, no credentials. Only exact accepted records from an
operator-observed complete/partial inventory become 24h per-sender evidence.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.extensions import db
from app.integrations.iventas.template_inventory import (
    TemplateInventoryValidationError, parse_template_inventory,
    evaluate_template_coverage,
)
from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM as Binding,
    MarketingCampaignV2TemplateORM as Template,
    MarketingCampaignV2TemplateChannelEvidenceORM as Evidence,
)
from app.services.marketing_campaign_v2_dispatch_config_service import (
    template_allows_channel,
)
from app.services.marketing_campaign_v2_template_evidence_service import (
    _capture_time, _utc, MAX_INVENTORY_BYTES, MAX_INVENTORY_RECORDS,
    EVIDENCE_VALID_FOR,
)
from app.services.marketing_campaign_v2_template_probe_service import (
    _signature as template_version_signature,
)


class BulkInventoryValidation(ValueError):
    pass


def _sha(payload):
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def sender_signature(binding):
    return _sha([
        int(binding.id), int(binding.sucursal_id), str(binding.sucursal_canon),
        str(binding.provider), str(binding.provider_channel_id),
    ])


def _parse(inventory):
    if not isinstance(inventory, list) or not (1 <= len(inventory) <= MAX_INVENTORY_RECORDS):
        raise BulkInventoryValidation("Se requiere un inventario JSON de iVentas no vacío.")
    raw = json.dumps(inventory, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_INVENTORY_BYTES:
        raise BulkInventoryValidation("Inventario excede el límite de tamaño.")
    try:
        return parse_template_inventory(inventory), hashlib.sha256(raw).hexdigest()
    except TemplateInventoryValidationError as exc:
        raise BulkInventoryValidation(str(exc)) from exc


def _context(*, template_id, inventory, session, lock=False):
    if type(template_id) is not int or template_id <= 0:
        raise BulkInventoryValidation("Plantilla inválida.")
    template_query = session.query(Template).filter(Template.id == template_id)
    template = (template_query.with_for_update() if lock else template_query).one_or_none()
    if template is None or not template.is_active or template.provider != "IVENTAS":
        raise BulkInventoryValidation("Plantilla local de iVentas inexistente o inactiva.")
    records, inventory_sha = _parse(inventory)
    query = session.query(Binding).filter(
        Binding.provider == "IVENTAS", Binding.is_active.is_(True),
        Binding.is_default.is_(True),
    ).order_by(Binding.sucursal_canon, Binding.id)
    bindings = (query.with_for_update() if lock else query).all()
    if not bindings:
        raise BulkInventoryValidation("No hay canales emisores activos.")
    channels = sorted({str(binding.provider_channel_id) for binding in bindings})
    try:
        coverage = evaluate_template_coverage(
            inventory=records, expected_channel_ids=channels,
            template_names=[str(template.template_name)],
        )[str(template.template_name)]
    except TemplateInventoryValidationError as exc:
        raise BulkInventoryValidation(str(exc)) from exc
    signature = template_version_signature(template)
    rows = []
    for binding in bindings:
        channel = str(binding.provider_channel_id)
        compatible = template_allows_channel(template, channel)
        status = coverage[channel] if compatible else "incompatible"
        rows.append({
            "binding_id": int(binding.id),
            "sucursal_canon": str(binding.sucursal_canon),
            "channel_id": channel,
            "status": status,
            "compatible": compatible,
            "sender_signature": sender_signature(binding),
        })
    fingerprint = _sha({
        "template_id": template_id, "template_signature": signature,
        "inventory_sha256": inventory_sha,
        "rows": rows,
    })
    return template, rows, fingerprint, inventory_sha, signature


def preview_bulk_template_inventory(*, template_id, inventory, session=None):
    active = session if session is not None else db.session
    template, rows, fingerprint, _, _ = _context(
        template_id=template_id, inventory=inventory, session=active,
    )
    counts = {
        "accepted": sum(row["status"] == "accepted" for row in rows),
        "pending": sum(row["status"] == "not_observed" for row in rows),
        "rejected": sum(row["status"] not in {"accepted", "not_observed", "incompatible"} for row in rows),
        "incompatible": sum(row["status"] == "incompatible" for row in rows),
    }
    return {
        "template_id": int(template.id),
        "template_name": str(template.template_name),
        "rows": [{k: value for k, value in row.items() if k != "sender_signature"}
                 for row in rows],
        "counts": counts,
        "candidate_fingerprint": fingerprint,
        "provider_api_verified": False,
        "send_authorized": False,
        "provider_requests": 0,
    }


def register_bulk_template_inventory(
    *, template_id, inventory, observed_at, source_reference,
    confirmed_provider_capture, expected_fingerprint, actor_user_id,
    session=None, now=None,
):
    if confirmed_provider_capture is not True:
        raise BulkInventoryValidation("Confirma la consulta real del inventario iVentas.")
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise BulkInventoryValidation("Operador inválido.")
    if not isinstance(source_reference, str) or not (
        8 <= len(source_reference.strip()) <= 500
    ):
        raise BulkInventoryValidation("Se requiere referencia verificable de iVentas.")
    if not isinstance(expected_fingerprint, str) or len(expected_fingerprint) != 64:
        raise BulkInventoryValidation("Vista previa del inventario requerida.")
    timestamp = _utc(now or datetime.now(timezone.utc))
    try:
        capture_time = _capture_time(observed_at, timestamp)
    except ValueError as exc:
        raise BulkInventoryValidation(str(exc)) from exc
    active = session if session is not None else db.session
    if active.get_bind().dialect.name != "postgresql":
        raise BulkInventoryValidation("Registro de evidencia requiere PostgreSQL.")
    template, rows, fingerprint, inventory_sha, signature = _context(
        template_id=template_id, inventory=inventory, session=active, lock=True,
    )
    if fingerprint != expected_fingerprint:
        raise BulkInventoryValidation("Plantilla o canales cambiaron; revisa de nuevo.")
    observed = [row for row in rows if row["status"] not in {"not_observed", "incompatible"}]
    if not observed:
        raise BulkInventoryValidation("Ningún canal tiene un estado acreditado.")
    for row in observed:
        active.add(Evidence(
            template_id=int(template.id),
            provider_channel_id=row["channel_id"],
            sender_binding_id=row["binding_id"],
            template_signature=signature,
            sender_signature=row["sender_signature"],
            observed_status=row["status"],
            inventory_sha256=inventory_sha,
            source_reference=source_reference.strip(),
            observed_at=capture_time,
            expires_at=capture_time + EVIDENCE_VALID_FOR,
            captured_by_user_id=actor_user_id,
        ))
    active.commit()
    return {
        "template_id": int(template.id),
        "recorded": sum(row["status"] == "accepted" for row in observed),
        "revoked": sum(row["status"] != "accepted" for row in observed),
        "pending": len(rows) - len(observed),
        "expires_at": (capture_time + EVIDENCE_VALID_FOR).isoformat(),
        "provider_api_verified": False,
        "send_authorized": False,
        "quota_reserved": False,
    }


def bulk_evidence_channel_status(*, template, session, outbound_bindings, now=None):
    """Return accepted and explicitly nonaccepted senders, respecting newest observation."""
    timestamp = _utc(now or datetime.now(timezone.utc))
    requested = {}
    for item in outbound_bindings:
        channel = item.get("provider_channel_id")
        binding_id = item.get("channel_binding_id")
        if channel and binding_id:
            requested.setdefault(str(channel), set()).add(int(binding_id))
    if not requested:
        return frozenset(), frozenset()
    records = session.query(Evidence).filter(
        Evidence.template_id == int(template.id),
        Evidence.provider_channel_id.in_(sorted(requested)),
    ).order_by(Evidence.observed_at.desc(), Evidence.id.desc()).all()
    latest = {}
    for row in records:
        latest.setdefault((str(row.provider_channel_id), int(row.sender_binding_id)), row)
    accepted = set()
    nonaccepted = set()
    signature = template_version_signature(template)
    for channel, binding_ids in requested.items():
        statuses = []
        for ident in binding_ids:
            binding = session.get(Binding, ident)
            proof = latest.get((channel, ident))
            if (binding is None or not binding.is_active or not binding.is_default
                    or binding.provider != "IVENTAS"
                    or str(binding.provider_channel_id) != channel
                    or proof is None or proof.template_signature != signature
                    or proof.sender_signature != sender_signature(binding)
                    or _utc(proof.observed_at) > timestamp
                    or _utc(proof.expires_at) <= timestamp):
                statuses.append("unknown")
            else:
                statuses.append(str(proof.observed_status))
        if any(status not in {"accepted", "unknown"} for status in statuses):
            nonaccepted.add(channel)
        elif statuses and all(status == "accepted" for status in statuses):
            accepted.add(channel)
    return frozenset(accepted), frozenset(nonaccepted)


def accepted_bulk_evidence_channels(*, template, session, outbound_bindings, now=None):
    return bulk_evidence_channel_status(
        template=template, session=session,
        outbound_bindings=outbound_bindings, now=now,
    )[0]


def catalog_bulk_inventory_status(*, template_id, session=None, now=None):
    """Read persisted signed evidence, never imply a live iVentas query."""
    active = session if session is not None else db.session
    timestamp = _utc(now or datetime.now(timezone.utc))
    if type(template_id) is not int or template_id <= 0:
        raise BulkInventoryValidation("Plantilla inválida.")
    template = active.query(Template).filter(Template.id == template_id).one_or_none()
    if template is None or template.provider != "IVENTAS":
        raise BulkInventoryValidation("Plantilla local iVentas inexistente.")
    bindings = active.query(Binding).filter(
        Binding.provider == "IVENTAS", Binding.is_active.is_(True),
        Binding.is_default.is_(True),
    ).order_by(Binding.sucursal_canon, Binding.id).all()
    channels = sorted({str(binding.provider_channel_id) for binding in bindings})
    records = active.query(Evidence).filter(
        Evidence.template_id == template_id,
        Evidence.provider_channel_id.in_(channels),
    ).order_by(Evidence.observed_at.desc(), Evidence.id.desc()).all() if channels else []
    latest = {}
    for item in records:
        latest.setdefault((str(item.provider_channel_id), int(item.sender_binding_id)), item)
    signature = template_version_signature(template)
    rows = []
    for binding in bindings:
        channel = str(binding.provider_channel_id)
        compatible = template_allows_channel(template, channel)
        proof = latest.get((channel, int(binding.id)))
        if not compatible:
            status = "incompatible"
        elif proof is None:
            status = "not_observed"
        elif (proof.template_signature != signature
              or proof.sender_signature != sender_signature(binding)):
            status = "changed"
        elif _utc(proof.observed_at) > timestamp or _utc(proof.expires_at) <= timestamp:
            status = "expired"
        else:
            status = str(proof.observed_status)
        rows.append({
            "sucursal_canon": str(binding.sucursal_canon),
            "channel_id": channel, "status": status,
        })
    return {
        "template_id": template_id, "template_name": str(template.template_name),
        "rows": rows,
        "counts": {
            "accepted": sum(row["status"] == "accepted" for row in rows),
            "pending": sum(row["status"] != "accepted" for row in rows),
        },
        "provider_api_verified": False, "send_authorized": False,
    }
