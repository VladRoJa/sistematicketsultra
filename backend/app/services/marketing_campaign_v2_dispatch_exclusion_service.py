"""Audited campaign-only suppressions for frozen Campaign V2 dispatch.

These records do not change frozen recipients or the global blacklist.
Never clear exclusion rows automatically; any changes need a separate review.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2DispatchApprovalORM,
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
    inspect_rejected: bool = False,
    unconfirmed_batches: list[dict[str, Any]] | None = None,
) -> set[str]:
    """Proof of actual provider submissions, never the source frozen cohort.

    Each accepted provider child retains the exact leads in request_snapshot_json.
    Accept only proven SUBMITTED snapshots; audited HELD children contributed
    zero submitted contacts. Untouched READY children count as zero; any\n    attempt, partial response or ambiguous result still fails closed.
    """
    children = (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == source_campaign_id)
        .all()
    )
    if not children:
        raise CampaignV2ScopedExclusionValidationError(
            "La campaña origen no tiene lotes auditados."
        )

    submitted = []
    for child in children:
        if child.status == "READY":
            # A prepared READY child is not proof of a provider submission.
            # Ignore it ONLY if its persistence has no sign of an attempt,
            # result, reconciliation or retry. Otherwise fail closed.
            if (
                child.provider_campaign_id is not None
                or child.submit_started_at is not None
                or child.submitted_at is not None
                or getattr(child, "provider_send_at", None) is not None
                or getattr(child, "provider_response_json", None)
                or getattr(child, "provider_deduplicated", None) is not None
                or getattr(child, "error_code", None) is not None
                or getattr(child, "support_ref", None) is not None
                or getattr(child, "reconciliation_resolution", None) is not None
                or getattr(child, "reconciled_at", None) is not None
                or getattr(child, "reconciliation_note", None) is not None
                or getattr(child, "reconciliation_snapshot_json", None)
                or getattr(child, "retry_attempt_count", 0) not in (None, 0)
                or getattr(child, "retry_last_attempt_at", None) is not None
                or getattr(child, "retry_history_json", None)
            ):
                raise CampaignV2ScopedExclusionValidationError(
                    "Origen contiene lote READY con indicios de envío; revisión obligatoria."
                )
            continue
        if child.status == "HELD":
            # A held batch is an intentional *non-send*, not a prior contact.
            # Require its persisted audit; reject any provider attempt/identity.
            if (
                child.hold_reason != "CHANNEL_DAILY_QUOTA"
                or not child.held_by_user_id
                or child.held_at is None
                or not isinstance(child.hold_evidence_json, dict)
                or not child.hold_evidence_json
                or child.provider_campaign_id is not None
                or child.submit_started_at is not None
                or child.submitted_at is not None
            ):
                raise CampaignV2ScopedExclusionValidationError(
                    "Origen con lote HELD sin auditoría íntegra o con intento de envío."
                )
            continue
        if child.status == "PROVIDER_ERROR" and inspect_rejected:
            # This exception is ONLY for audited contact-overlap review.
            # A 400 TEMPLATE_NOT_FOUND is not an accepted provider submission,
            # yet can create a provider-side record. Keep it unresolved and
            # visible; never infer delivery OR absence of delivery.
            response = getattr(child, "provider_response_json", None)
            if (
                child.error_code != "TEMPLATE_NOT_FOUND"
                or not isinstance(response, dict)
                or response.get("http_status") != 400
                or not getattr(child, "support_ref", None)
                or child.provider_campaign_id is not None
                or child.submitted_at is not None
                or child.submit_started_at is None
            ):
                raise CampaignV2ScopedExclusionValidationError(
                    "Origen tiene resultado proveedor no confirmado; requiere revisión manual."
                )
            if unconfirmed_batches is not None:
                unconfirmed_batches.append({
                    "source_campaign_id": source_campaign_id,
                    "child_id": int(child.id),
                    "status": child.status,
                    "error_code": child.error_code,
                    "recipient_count": int(child.recipient_count),
                })
            continue
        if (
            child.status != "SUBMITTED"
            or not child.provider_campaign_id
            or child.submitted_at is None
        ):
            raise CampaignV2ScopedExclusionValidationError(
                "Origen contiene lotes sin aceptación demostrada por iVentas."
            )
        submitted.append(child)
    if not submitted:
        raise CampaignV2ScopedExclusionValidationError(
            "El origen no tiene contactos SUBMITTED demostrables."
        )

    phones: set[str] = set()
    for child in submitted:
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
    allow_later_frozen_source: bool = False,
    inspect_rejected: bool = False,
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
    ):
        raise CampaignV2ScopedExclusionValidationError(
            "Origen y destino deben estar congelados."
        )
    if source.frozen_at >= target.frozen_at:
        if not allow_later_frozen_source:
            raise CampaignV2ScopedExclusionValidationError(
                "La campaña origen debe estar congelada antes de la campaña destino."
            )
        # A later source can be used only while the target still has NO
        # provider children and NO approved dispatch. The write repeats
        # these guards under a campaign row lock.
        children_exist = active.query(MarketingCampaignV2ProviderCampaignORM.id).filter(
            MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id,
        ).first()
        approved = active.query(MarketingCampaignV2DispatchApprovalORM.id).filter(
            MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == campaign_id,
        ).first()
        if children_exist or approved:
            raise CampaignV2ScopedExclusionValidationError(
                "No se permite usar un origen posterior si el destino ya tiene lotes o aprobación."
            )

    unconfirmed_batches: list[dict[str, Any]] = []
    submitted_phones = _submitted_phone_set(
        source_campaign_id=source_campaign_id, session=active,
        inspect_rejected=inspect_rejected,
        unconfirmed_batches=unconfirmed_batches,
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
        "unconfirmed_batches": unconfirmed_batches,
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
