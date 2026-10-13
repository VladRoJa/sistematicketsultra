"""D3c2 — derived cohorts cannot reuse a phone in another possible provider send.

Derived-only fail-closed guard. Re-run from the ordinary V2 preflight so D2a,
D2b and D2c cannot rely on a stale materialization-time deduplication check.
A global advisory lock serializes D3c2 freezes; HTTP is never performed here.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_blacklist_service import get_blacklisted_phones
from app.services.marketing_phone import normalize_phone

DERIVED_SOURCE = "HELD_RELEASE_DERIVED"
POSSIBLY_CONTACTED = (
    "SUBMITTING", "SUBMITTED", "SCHEDULED", "RECONCILIATION_REQUIRED",
    "RETRY_ELIGIBLE", "RETRY_EXHAUSTED", "PROVIDER_ERROR",
)


class DerivedContactConflict(RuntimeError):
    pass


def assert_no_prior_or_pending_contact(
    *, phones: Iterable[str], session: Any, exclude_campaign_id: int | None = None,
) -> None:
    normalized = tuple(str(x) for x in phones)
    if not normalized or len(set(normalized)) != len(normalized) or any(
        normalize_phone(p) != p or len(p) != 10 for p in normalized
    ):
        raise DerivedContactConflict("La cohorte contiene teléfonos duplicados o inválidos.")
    desired = set(normalized)
    blacklisted = get_blacklisted_phones(phones=desired, session=session)
    if desired & blacklisted:
        raise DerivedContactConflict("La lista negra cambió; volver a revisar la cohorte.")

    # Stop if another derived freeze already claims any same contact, even if
    # its dispatch has not begun. A partial cohort must not be copied silently.
    derived = session.query(MarketingCampaignV2RecipientORM).join(
        MarketingCampaignV2ORM,
        MarketingCampaignV2ORM.id == MarketingCampaignV2RecipientORM.campaign_id,
    ).filter(
        MarketingCampaignV2ORM.source == DERIVED_SOURCE,
        *(
            (MarketingCampaignV2ORM.id != exclude_campaign_id,)
            if exclude_campaign_id is not None else ()
        ),
    ).all()
    if any(str(r.phone_mx10) in desired for r in derived):
        raise DerivedContactConflict("Un contacto ya pertenece a otra cohorte derivada.")

    # The provider's per-child snapshot is the evidence of actual/potential
    # contact, not merely the earlier campaign's whole frozen population.
    attempted = session.query(MarketingCampaignV2ProviderCampaignORM).filter(
        MarketingCampaignV2ProviderCampaignORM.status.in_(POSSIBLY_CONTACTED),
        *(
            (MarketingCampaignV2ProviderCampaignORM.campaign_v2_id != exclude_campaign_id,)
            if exclude_campaign_id is not None else ()
        ),
    ).all()
    for child in attempted:
        if (child.status == "PROVIDER_ERROR" and
                child.reconciliation_resolution == "NOT_CREATED_CONFIRMED"):
            continue
        payload = child.request_snapshot_json
        leads = payload.get("leads") if isinstance(payload, dict) else None
        if (not isinstance(leads, list) or len(leads) != int(child.recipient_count)
                or not leads):
            raise DerivedContactConflict(
                "Otro envío tiene snapshot incompleto; revisar antes de liberar HELD."
            )
        seen = set()
        for lead in leads:
            raw = lead.get("phone") if isinstance(lead, dict) else None
            phone = normalize_phone(raw)
            if phone is None or phone in seen:
                raise DerivedContactConflict("Otro envío contiene contactos no verificables.")
            seen.add(phone)
        if desired & seen:
            raise DerivedContactConflict(
                "Destinatario coincidente con otro envío previo o en proceso."
            )
