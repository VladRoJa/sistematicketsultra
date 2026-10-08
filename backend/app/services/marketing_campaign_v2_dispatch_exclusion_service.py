"""Audited campaign-only suppressions for frozen Campaign V2 dispatch.

These records do not change frozen recipients or the global blacklist.
Never clear exclusion rows automatically; any changes need a separate review.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2RecipientORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientDispatchExclusionORM,
)
from app.services.marketing_campaign_v2_query_service import get_campaign_v2
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)

AMBIGUOUS_BRANCH_EVIDENCE = "AMBIGUOUS_BRANCH_EVIDENCE"


class CampaignV2ScopedExclusionValidationError(ValueError):
    pass


def get_campaign_v2_excluded_recipient_ids(
    *,
    campaign_id: int,
    session: Any | None = None,
) -> set[int]:
    """Read exclusions scoped to the *same* frozen campaign as the recipient."""
    active = session if session is not None else db.session
    rows = (
        active.query(MarketingCampaignV2RecipientDispatchExclusionORM.recipient_id)
        .join(
            MarketingCampaignV2RecipientORM,
            MarketingCampaignV2RecipientORM.id ==
            MarketingCampaignV2RecipientDispatchExclusionORM.recipient_id,
        )
        .filter(
            MarketingCampaignV2RecipientDispatchExclusionORM.campaign_id == campaign_id,
            MarketingCampaignV2RecipientORM.campaign_id == campaign_id,
        )
        .all()
    )
    return {int(recipient_id) for (recipient_id,) in rows}


def add_campaign_v2_ambiguous_branch_exclusions(
    *,
    campaign_id: int,
    recipient_ids: Iterable[int],
    actor_user_id: int,
    allowed_sucursal_keys,
    session: Any | None = None,
) -> dict[str, Any]:
    """Stage exclusions in the transaction of an authorized operator.

    Caller must commit explicitly. This helper never sends or touches global
    blacklist. It also fails if provider children exist, to avoid changing an
    already attempted dispatch's recipients/fingerprint.
    """
    active = session if session is not None else db.session
    ids = tuple(recipient_ids)
    if (
        type(campaign_id) is not int or campaign_id <= 0
        or type(actor_user_id) is not int or actor_user_id <= 0
        or not ids or len(set(ids)) != len(ids)
        or any(type(value) is not int or value <= 0 for value in ids)
    ):
        raise CampaignV2ScopedExclusionValidationError(
            "campaign_id, actor_user_id e IDs de destinatarios deben ser válidos y únicos."
        )

    # Enforce frozen cohort visibility and lock the campaign against
    # concurrent operator edits; backend—not Angular—controls permissions.
    get_campaign_v2(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=active,
    )
    campaign = (
        active.query(MarketingCampaignV2ORM)
        .filter(MarketingCampaignV2ORM.id == campaign_id)
        .with_for_update()
        .one()
    )
    if not campaign.frozen_at:
        raise CampaignV2ScopedExclusionValidationError("La campaña no está congelada.")
    if (
        active.query(MarketingCampaignV2ProviderCampaignORM.id)
        .filter(MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id)
        .first()
    ):
        raise CampaignV2ScopedExclusionValidationError(
            "La campaña ya tiene provider children; no se permiten cambios de audiencia."
        )
    recipients = (
        active.query(MarketingCampaignV2RecipientORM)
        .filter(
            MarketingCampaignV2RecipientORM.campaign_id == campaign_id,
            MarketingCampaignV2RecipientORM.id.in_(ids),
        )
        .all()
    )
    by_id = {int(item.id): item for item in recipients}
    if set(by_id) != set(ids):
        raise CampaignV2ScopedExclusionValidationError(
            "Algún destinatario no pertenece a la campaña congelada."
        )

    existing = get_campaign_v2_excluded_recipient_ids(
        campaign_id=campaign_id, session=active,
    )
    for recipient_id in ids:
        recipient = by_id[recipient_id]
        if recipient.sucursal is not None:
            raise CampaignV2ScopedExclusionValidationError(
                f"El destinatario {recipient_id} ya tiene sucursal definida."
            )
        keys = {
            key
            for evidence in recipient.evidence_rows
            if (key := normalize_socios_vencidos_branch_key(evidence.sucursal_key))
        }
        if len(keys) < 2:
            raise CampaignV2ScopedExclusionValidationError(
                f"El destinatario {recipient_id} no tiene evidencias conflictivas."
            )

    for recipient_id in ids:
        if recipient_id not in existing:
            active.add(MarketingCampaignV2RecipientDispatchExclusionORM(
                campaign_id=campaign_id,
                recipient_id=recipient_id,
                reason=AMBIGUOUS_BRANCH_EVIDENCE,
                created_by_user_id=actor_user_id,
            ))
    active.flush()
    return {
        "campaign_id": campaign_id,
        "excluded_recipient_ids": sorted(ids),
        "added": len(set(ids) - existing),
        "already_present": len(set(ids) & existing),
    }
