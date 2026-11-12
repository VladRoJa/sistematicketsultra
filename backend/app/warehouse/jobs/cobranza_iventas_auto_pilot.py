"""One-day, one-branch governed auto dispatch for the Nov 12 cobranza pilot.

Disabled by default. Never performs provider HTTP; the existing background
worker owns execution. No other branch or date can be auto-sent by this module.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ORM, MarketingCampaignV2RecipientORM
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_cobranza_send_service import enqueue_cobranza_send

PILOT_DATE = date(2026, 11, 12)
PILOT_BRANCH = "VILLAS_DEL_REY"
DISPATCH_FLAGS = (
    "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED",
    "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY",
    "CAMPAIGN_V2_PROVIDER_SEND_ENABLED",
    "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED",
)


class AutoPilotBlocked(ValueError):
    """Closed without queueing or calling the provider."""


@dataclass(frozen=True)
class AutoPilotConfig:
    max_recipients: int
    operator_id: int


def auto_pilot_config(day: date) -> AutoPilotConfig | None:
    """No action outside a single explicitly configured business date."""
    if os.getenv("COBRANZA_IVENTAS_AUTO_SEND_ENABLED", "").lower().strip() != "true":
        return None
    if day != PILOT_DATE:
        return None
    if os.getenv("COBRANZA_IVENTAS_AUTO_SEND_DATE", "").strip() != PILOT_DATE.isoformat():
        raise AutoPilotBlocked("Fecha de autorización del piloto no coincide.")
    if os.getenv("COBRANZA_IVENTAS_AUTO_SEND_BRANCH", "").strip() != PILOT_BRANCH:
        raise AutoPilotBlocked("La sucursal autorizada no coincide.")
    try:
        limit = int(os.environ["COBRANZA_IVENTAS_AUTO_SEND_MAX_RECIPIENTS"])
        operator = int(os.environ["COBRANZA_IVENTAS_AUTO_SEND_OPERATOR_ID"])
    except (KeyError, ValueError) as exc:
        raise AutoPilotBlocked("Falta autorización técnica o límite de destinatarios.") from exc
    if not 1 <= limit <= 30 or operator <= 0:
        raise AutoPilotBlocked("Límite o identidad técnica inválidos.")
    return AutoPilotConfig(max_recipients=limit, operator_id=operator)


def queue_auto_pilot(*, day: date, campaign_id: int, settings: AutoPilotConfig) -> dict:
    """Apply the same preflight, quota, approval and idempotency as the button."""
    if day != PILOT_DATE or not isinstance(settings, AutoPilotConfig):
        raise AutoPilotBlocked("Fecha de piloto inválida.")
    if not all(current_app.config.get(flag) is True for flag in DISPATCH_FLAGS):
        raise AutoPilotBlocked("El envío gobernado no está habilitado en el scheduler.")

    campaign = db.session.get(MarketingCampaignV2ORM, campaign_id)
    meta = ((campaign.audience_definition_json or {}).get("source_metadata") or {}) if campaign else {}
    if (
        not campaign
        or meta.get("automation_job") != "cobranza_recurrente_rechazados"
        or meta.get("business_date") != day.isoformat()
        or meta.get("pilot_branch_key") != PILOT_BRANCH
        or meta.get("auto_pilot_date") != day.isoformat()
    ):
        raise AutoPilotBlocked("La campaña no corresponde al piloto autorizado.")
    total = int(db.session.query(func.count(MarketingCampaignV2RecipientORM.id)).filter(
        MarketingCampaignV2RecipientORM.campaign_id == campaign_id
    ).scalar() or 0)
    if not 1 <= total <= settings.max_recipients:
        raise AutoPilotBlocked("Destinatarios exceden el límite autorizado.")

    actor = db.session.get(UserORM, settings.operator_id)
    try:
        access = resolve_marketing_access(actor)
    except Exception as exc:
        raise AutoPilotBlocked("La identidad técnica no dispone de permisos.") from exc
    if not (
        access.is_global
        and access.can_manage_campaigns
        and access.can_preflight_campaigns
        and access.can_manage_dispatch_config
        and access.can_send_campaigns
    ):
        raise AutoPilotBlocked("La identidad técnica carece de permisos de envío.")
    return enqueue_cobranza_send(
        campaign_id=campaign_id,
        actor_user_id=settings.operator_id,
        allowed_sucursal_keys=None,
        session=db.session,
    )


def mark_auto_pilot_blocked(campaign_id: int) -> None:
    """Durable, safe status for the operator popup if no job could be queued."""
    campaign = db.session.get(MarketingCampaignV2ORM, campaign_id)
    if campaign is None:
        return
    doc = dict(campaign.audience_definition_json or {})
    meta = dict(doc.get("source_metadata") or {})
    if meta.get("auto_pilot_date") != PILOT_DATE.isoformat():
        return
    meta["auto_pilot_blocked"] = True
    doc["source_metadata"] = meta
    campaign.audience_definition_json = doc
    db.session.commit()
