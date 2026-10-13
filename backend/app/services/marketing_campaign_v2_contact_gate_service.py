"""SEC-856-QA-01: one PostgreSQL contact gate shared by freeze and outbound.

This is a *transaction-scoped* admission lock, not a lock held during HTTP.
Every sending path obtains it before durably claiming SUBMITTING. D3c2
freezing obtains the same lock before evaluating/creating its derived cohort.
The losing transaction re-reads committed contact state while it owns the
lock; a stale preflight alone never grants permission.

Historical non-derived marketing campaigns retain their existing repeat
contact policy. A derived HELD cohort, however, is exclusive against every
other provider attempt, and all V2 sends must respect that exclusivity.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_derived_contact_guard import (
    DERIVED_SOURCE,
    DerivedContactConflict,
    assert_no_prior_or_pending_contact,
)
from app.services.marketing_phone import (
    format_mexico_international_phone,
    normalize_phone,
)

CONTACT_GATE_SCOPE = "mkt_v2_d3c2:freeze_all_derived"


class CampaignV2ContactGateConflict(RuntimeError):
    pass


def acquire_campaign_v2_contact_gate(session: Any) -> None:
    """Acquire BEFORE campaign/child locks; caller commits only after claim."""
    if session.get_bind().dialect.name != "postgresql":
        raise CampaignV2ContactGateConflict(
            "La protección cruzada de contactos requiere PostgreSQL."
        )
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": CONTACT_GATE_SCOPE},
    )


def _claim_phones(child: MarketingCampaignV2ProviderCampaignORM) -> tuple[str, ...]:
    snapshot = child.request_snapshot_json
    leads = snapshot.get("leads") if isinstance(snapshot, dict) else None
    if not isinstance(leads, list) or not leads or len(leads) != int(child.recipient_count):
        raise CampaignV2ContactGateConflict("Snapshot provider ausente o incompleto.")
    if snapshot.get("provider_channel_id") != child.provider_channel_id:
        raise CampaignV2ContactGateConflict("Canal del snapshot provider incompatible.")
    phones: list[str] = []
    for lead in leads:
        raw = lead.get("phone") if isinstance(lead, dict) else None
        phone = normalize_phone(raw)
        if (phone is None or not isinstance(raw, str) or
                format_mexico_international_phone(phone) != raw):
            raise CampaignV2ContactGateConflict(
                "Identidad telefónica del snapshot provider no verificable."
            )
        phones.append(phone)
    if len(set(phones)) != len(phones):
        raise CampaignV2ContactGateConflict("Teléfonos duplicados en child.")
    return tuple(phones)


def verify_outbound_contact_admission(
    *, child: MarketingCampaignV2ProviderCampaignORM, session: Any,
) -> None:
    """Must run under acquire_campaign_v2_contact_gate, before SUBMITTING commit.

    Caller holds the common lock. We require a verified child snapshot rather
    than trusting the request body or a preflight captured before waiting.
    """
    campaign = session.get(MarketingCampaignV2ORM, int(child.campaign_v2_id))
    if campaign is None:
        raise CampaignV2ContactGateConflict("Campaña del child inexistente.")
    phones = _claim_phones(child)
    desired = set(phones)
    if campaign.source == DERIVED_SOURCE:
        try:
            assert_no_prior_or_pending_contact(
                phones=phones, session=session,
                exclude_campaign_id=int(child.campaign_v2_id),
            )
        except DerivedContactConflict as exc:
            raise CampaignV2ContactGateConflict(str(exc)) from exc
        return

    # Non-derived sends remain compatible with their previous repeat-contact
    # policy, but cannot race a HELD-derived freeze or resend its contacts.
    derived = session.query(MarketingCampaignV2RecipientORM).join(
        MarketingCampaignV2ORM,
        MarketingCampaignV2ORM.id == MarketingCampaignV2RecipientORM.campaign_id,
    ).filter(
        MarketingCampaignV2ORM.source == DERIVED_SOURCE,
        MarketingCampaignV2ORM.id != int(child.campaign_v2_id),
    ).all()
    if any(str(r.phone_mx10) in desired for r in derived):
        raise CampaignV2ContactGateConflict(
            "Destinatario reservado por una cohorte HELD derivada."
        )
