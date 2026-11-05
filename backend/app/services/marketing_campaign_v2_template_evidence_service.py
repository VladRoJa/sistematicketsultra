"""Operator-attested iVentas template inventory for frozen failed-cohort dispatch.

This is NOT an authenticated provider API. Only a global dispatch operator may
register evidence copied from iVentas; every record is attributable, scoped and
expires. No provider requests, send approvals or quota reservations occur here.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.extensions import db
from app.integrations.iventas.template_inventory import (
    TemplateInventoryValidationError, evaluate_template_coverage,
    parse_template_inventory,
)
from app.models.marketing import (
    MarketingCampaignV2ORM, MarketingCampaignV2TemplateORM,
    MarketingCampaignV2TemplateEvidenceORM,
)
from app.services.marketing_campaign_v2_failed_cohort_service import FAILED_RECOVERY_SOURCE

MAX_INVENTORY_RECORDS = 2000
MAX_INVENTORY_BYTES = 750_000
MAX_CAPTURE_AGE = timedelta(hours=1)
EVIDENCE_VALID_FOR = timedelta(hours=24)


class TemplateEvidenceValidation(ValueError):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TemplateEvidenceValidation("Fecha de captura sin zona horaria.")
    return value.astimezone(timezone.utc)


def _capture_time(value: Any, now: datetime) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TemplateEvidenceValidation("Indica fecha y hora ISO de captura en iVentas.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise TemplateEvidenceValidation("Fecha de captura inválida.") from exc
    stamp = _utc(parsed)
    if stamp > now + timedelta(minutes=2) or now - stamp > MAX_CAPTURE_AGE:
        raise TemplateEvidenceValidation(
            "La evidencia debe tener menos de una hora y no puede ser futura."
        )
    return stamp


def template_signature(template: Any) -> str:
    payload = {
        "id": int(template.id),
        "name": str(template.template_name),
        "variables": template.variables_json or {},
        "channels": template.compatible_channel_ids_json or [],
    }
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


def binding_signature(bindings: list[dict[str, Any]]) -> str:
    """Bind evidence to every commercial branch and effective sender identity."""
    stable = sorted((
        int(b["sucursal_id"]),
        str(b["sucursal_canon"]),
        int(b["channel_binding_id"] or 0),
        str(b["provider_channel_id"] or ""),
        str(b["send_via_sucursal_canon"] or ""),
    ) for b in bindings)
    return hashlib.sha256(json.dumps(
        stable, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


def accepted_evidence_channels(
    *, campaign_id: int, template: Any, session: Any,
    required_binding_signature: str,
    now: datetime | None = None,
) -> frozenset[str]:
    timestamp = _utc(now or datetime.now(timezone.utc))
    row = (session.query(MarketingCampaignV2TemplateEvidenceORM)
           .filter_by(campaign_id=int(campaign_id), template_id=int(template.id))
           .order_by(MarketingCampaignV2TemplateEvidenceORM.id.desc()).first())
    if row is None or _utc(row.observed_at) > timestamp or _utc(row.expires_at) <= timestamp:
        return frozenset()
    if (row.template_signature != template_signature(template)
            or row.binding_signature != required_binding_signature):
        return frozenset()
    if str(row.template_name).casefold() != str(template.template_name).casefold():
        return frozenset()
    pairs = row.accepted_channel_ids_json
    if not isinstance(pairs, list) or not all(isinstance(x, str) for x in pairs):
        return frozenset()
    return frozenset(pairs)


def register_template_evidence(
    *, campaign_id: int, template_id: Any, inventory: Any,
    observed_at: Any, source_reference: Any, confirmed_provider_capture: Any,
    actor_user_id: int, session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active = session if session is not None else db.session
    timestamp = _utc(now or datetime.now(timezone.utc))
    if (not isinstance(template_id, int) or isinstance(template_id, bool) or template_id <= 0
            or not isinstance(campaign_id, int) or campaign_id <= 0
            or not isinstance(actor_user_id, int) or actor_user_id <= 0):
        raise TemplateEvidenceValidation("Campaña, plantilla o actor inválidos.")
    if confirmed_provider_capture is not True:
        raise TemplateEvidenceValidation("Debe confirmarse que el inventario procede de iVentas.")
    if not isinstance(source_reference, str) or not (8 <= len(source_reference.strip()) <= 500):
        raise TemplateEvidenceValidation("Indica referencia comprobable de la captura en iVentas.")
    if not isinstance(inventory, list) or not (1 <= len(inventory) <= MAX_INVENTORY_RECORDS):
        raise TemplateEvidenceValidation("Inventario de iVentas ausente o excesivo.")
    raw = json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_INVENTORY_BYTES:
        raise TemplateEvidenceValidation("Inventario excede el tamaño permitido.")
    capture_time = _capture_time(observed_at, timestamp)
    try:
        records = parse_template_inventory(inventory)
    except TemplateInventoryValidationError as exc:
        raise TemplateEvidenceValidation(str(exc)) from exc
    campaign = active.get(MarketingCampaignV2ORM, campaign_id)
    template = active.get(MarketingCampaignV2TemplateORM, template_id)
    if campaign is None or campaign.source != FAILED_RECOVERY_SOURCE:
        raise TemplateEvidenceValidation("Solo campañas de recuperación fallida congeladas.")
    if template is None or not template.is_active or template.provider != "IVENTAS":
        raise TemplateEvidenceValidation("Plantilla local inactiva o inexistente.")
    # The same canonical branch resolver, frozen recipients and sender route are
    # used for the evidence and for the eventual provider dispatch.
    from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
    plan = build_campaign_v2_preflight(
        campaign_id=campaign_id, template_id=template_id,
        allowed_sucursal_keys=None, session=active, now=timestamp,
    )
    if not plan.batches or any(not b.provider_channel_id for b in plan.batches):
        raise TemplateEvidenceValidation("Faltan canales de envío para la campaña.")
    channels = sorted({str(b.provider_channel_id) for b in plan.batches})
    try:
        coverage = evaluate_template_coverage(
            inventory=records, expected_channel_ids=channels,
            template_names=[str(template.template_name)],
        )
    except TemplateInventoryValidationError as exc:
        raise TemplateEvidenceValidation(str(exc)) from exc
    statuses = coverage[str(template.template_name)]
    rejected = {c: status for c, status in statuses.items() if status != "accepted"}
    if rejected:
        raise TemplateEvidenceValidation(
            "Plantilla sin aprobación explícita en estos canales: " +
            ", ".join(f"{channel} ({status})" for channel, status in rejected.items())
        )
    outbound_bindings = [
        {
            "sucursal_id": batch.sucursal_id,
            "sucursal_canon": batch.sucursal_canon,
            "channel_binding_id": batch.channel_binding_id,
            "provider_channel_id": batch.provider_channel_id,
            "send_via_sucursal_canon": batch.send_via_sucursal_canon,
        } for batch in plan.batches
    ]
    row = MarketingCampaignV2TemplateEvidenceORM(
        campaign_id=campaign_id, template_id=template_id,
        template_name=template.template_name,
        template_signature=template_signature(template),
        binding_signature=binding_signature(outbound_bindings),
        accepted_channel_ids_json=channels,
        inventory_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        source_reference=source_reference.strip(),
        observed_at=capture_time,
        expires_at=capture_time + EVIDENCE_VALID_FOR,
        captured_by_user_id=actor_user_id,
        created_at=timestamp,
    )
    active.add(row)
    active.commit()
    return {
        "id": int(row.id), "campaign_id": campaign_id, "template_id": template_id,
        "template_name": str(template.template_name),
        "accepted_channel_ids": channels,
        "inventory_sha256": row.inventory_sha256,
        "observed_at": capture_time.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "source": "OPERATOR_ATTESTED_IVENTAS_EXPORT",
        "provider_api_verified": False,
        "send_authorized": False,
        "quota_reserved": False,
    }
