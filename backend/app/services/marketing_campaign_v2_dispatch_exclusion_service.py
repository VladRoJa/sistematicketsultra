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
from app.services.marketing_phone import format_mexico_international_phone, normalize_phone
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


PREVIOUS_CAMPAIGN_CONTACT = "PREVIOUS_CAMPAIGN_CONTACT"


def _submitted_phone_set(
    *, source_campaign_id: int, session: Any,
) -> set[str]:
    """Proof of actual provider submissions, never the source frozen cohort.

    Each accepted provider child retains the exact leads in request_snapshot_json.
    Reject partial/ambiguous dispatches and incomplete snapshots rather than
    guessing which recipient the prior provider accepted.
    """
    children = (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == source_campaign_id)
        .all()
    )
    if not children or any(
        child.status != "SUBMITTED"
        or not child.provider_campaign_id
        or child.submitted_at is None
        for child in children
    ):
        raise CampaignV2ScopedExclusionValidationError(
            "La campaña de origen no tiene todos sus lotes SUBMITTED."
        )

    phones: set[str] = set()
    for child in children:
        snapshot = child.request_snapshot_json
        leads = snapshot.get("leads") if isinstance(snapshot, dict) else None
        if (
            not isinstance(leads, list)
            or len(leads) != int(child.recipient_count)
            or not leads
        ):
            raise CampaignV2ScopedExclusionValidationError(
                "Snapshot de envío anterior incompleto o inconsistente."
            )
        if snapshot.get("provider_channel_id") != child.provider_channel_id:
            raise CampaignV2ScopedExclusionValidationError(
                "Canal del snapshot anterior no coincide con el lote aceptado."
            )
        for lead in leads:
            raw = lead.get("phone") if isinstance(lead, dict) else None
            phone = normalize_phone(raw)
            if (
                phone is None
                or not isinstance(raw, str)
                or format_mexico_international_phone(phone) != raw
                or phone in phones
            ):
                raise CampaignV2ScopedExclusionValidationError(
                    "Identidad telefónica duplicada o inválida en el envío anterior."
                )
            phones.add(phone)
    return phones


def find_previous_campaign_contact_ids(
    *,
    campaign_id: int,
    source_campaign_id: int,
    allowed_sucursal_keys,
    session: Any | None = None,
) -> dict[str, Any]:
    """Read-only proof of overlapping numbers present in prior SUBMITTED payloads."""
    active = session if session is not None else db.session
    if (
        type(campaign_id) is not int or campaign_id <= 0
        or type(source_campaign_id) is not int or source_campaign_id <= 0
        or campaign_id == source_campaign_id
    ):
        raise CampaignV2ScopedExclusionValidationError(
            "Campañas de destino y origen deben ser IDs distintos y válidos."
        )

    # Scope authorization is checked for BOTH campaigns, not just the target.
    get_campaign_v2(
        campaign_id=campaign_id, allowed_sucursal_keys=allowed_sucursal_keys,
        session=active,
    )
    get_campaign_v2(
        campaign_id=source_campaign_id, allowed_sucursal_keys=allowed_sucursal_keys,
        session=active,
    )
    target = active.get(MarketingCampaignV2ORM, campaign_id)
    source = active.get(MarketingCampaignV2ORM, source_campaign_id)
    if (
        target is None or source is None
        or target.frozen_at is None or source.frozen_at is None
        or source.frozen_at >= target.frozen_at
    ):
        raise CampaignV2ScopedExclusionValidationError(
            "La campaña origen debe estar congelada antes de la campaña destino."
        )

    submitted_phones = _submitted_phone_set(
        source_campaign_id=source_campaign_id, session=active,
    )
    target_rows = (
        active.query(MarketingCampaignV2RecipientORM.id,
                     MarketingCampaignV2RecipientORM.phone_mx10)
        .filter(MarketingCampaignV2RecipientORM.campaign_id == campaign_id)
        .all()
    )
    ids = sorted(int(recipient_id) for recipient_id, phone in target_rows
                 if str(phone) in submitted_phones)
    return {
        "campaign_id": campaign_id,
        "source_campaign_id": source_campaign_id,
        "source_submitted_phones_count": len(submitted_phones),
        "matched_recipient_ids": ids,
        "matched": len(ids),
    }


def add_campaign_v2_previous_campaign_contact_exclusions(
    *,
    campaign_id: int,
    source_campaign_id: int,
    actor_user_id: int,
    expected_count: int,
    allowed_sucursal_keys,
    session: Any | None = None,
) -> dict[str, Any]:
    """Stage traceable per-campaign exclusions; caller explicitly commits.

    This operation never contacts the provider and never changes the frozen
    cohort or global blacklist. Do not invoke from a read-only preflight.
    """
    active = session if session is not None else db.session
    if (
        type(actor_user_id) is not int or actor_user_id <= 0
        or type(expected_count) is not int or expected_count <= 0
    ):
        raise CampaignV2ScopedExclusionValidationError(
            "Actor y cantidad esperada deben ser enteros positivos."
        )
    proof = find_previous_campaign_contact_ids(
        campaign_id=campaign_id, source_campaign_id=source_campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys, session=active,
    )
    if proof["matched"] != expected_count:
        raise CampaignV2ScopedExclusionValidationError(
            "La cantidad de coincidencias cambió; se requiere nueva revisión."
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
            "La campaña destino ya tiene provider children; no se pueden excluir contactos."
        )

    ids = proof["matched_recipient_ids"]
    rows = (
        active.query(MarketingCampaignV2RecipientDispatchExclusionORM)
        .filter(
            MarketingCampaignV2RecipientDispatchExclusionORM.campaign_id == campaign_id,
            MarketingCampaignV2RecipientDispatchExclusionORM.recipient_id.in_(ids),
        )
        .all()
    )
    existing = {int(row.recipient_id): row for row in rows}
    for row in rows:
        if (
            row.reason != PREVIOUS_CAMPAIGN_CONTACT
            or row.related_campaign_id != source_campaign_id
        ):
            raise CampaignV2ScopedExclusionValidationError(
                "Un destinatario tiene una exclusión por un motivo distinto."
            )
    for recipient_id in ids:
        if recipient_id not in existing:
            active.add(MarketingCampaignV2RecipientDispatchExclusionORM(
                campaign_id=campaign_id,
                recipient_id=recipient_id,
                reason=PREVIOUS_CAMPAIGN_CONTACT,
                related_campaign_id=source_campaign_id,
                created_by_user_id=actor_user_id,
            ))
    active.flush()
    return {
        **proof,
        "added": len(ids) - len(existing),
        "already_present": len(existing),
    }
