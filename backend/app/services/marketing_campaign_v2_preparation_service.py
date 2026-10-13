"""Read-only, auditable preflight preparation; never sends to a provider.

Phase C does not mutate frozen recipients, historical payloads or blacklist.
A write must have global management permission at the Flask route and a fresh
review signature, then stage only scoped dispatch exclusions in one transaction.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any

from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2RecipientORM,
    MarketingCampaignV2RecipientDispatchExclusionORM,
)
from app.services.marketing_campaign_v2_dispatch_exclusion_service import (
    AMBIGUOUS_BRANCH_EVIDENCE,
    PREVIOUS_CAMPAIGN_CONTACT,
    CampaignV2ScopedExclusionValidationError as ValidationError,
    add_campaign_v2_ambiguous_branch_exclusions,
    find_previous_campaign_contact_ids,
)
from app.services.marketing_campaign_v2_query_service import get_campaign_v2
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


def _fingerprint(kind: str, campaign_id: int, content: Any) -> str:
    encoded = json.dumps(
        [kind, campaign_id, content], ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ambiguous_rows(*, campaign_id: int, allowed_sucursal_keys, session: Any):
    get_campaign_v2(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys, session=session,
    )
    rows = session.query(MarketingCampaignV2RecipientORM).options(
        selectinload(MarketingCampaignV2RecipientORM.evidence_rows)
    ).filter(
        MarketingCampaignV2RecipientORM.campaign_id == campaign_id,
        MarketingCampaignV2RecipientORM.sucursal.is_(None),
    ).order_by(MarketingCampaignV2RecipientORM.id).all()
    grouped = []
    for recipient in rows:
        keys = sorted({
            key for evidence in recipient.evidence_rows
            if (key := normalize_socios_vencidos_branch_key(evidence.sucursal_key))
        })
        kind = (
            "AMBIGUOUS_EVIDENCE" if len(keys) >= 2
            else "MISSING_EVIDENCE" if not keys
            else "SINGLE_EVIDENCE_UNRESOLVED"
        )
        grouped.append({
            "recipient_id": int(recipient.id),
            "kind": kind,
            "branch_keys": keys,
        })
    return grouped


def review_ambiguous_branches(
    *,
    campaign_id: int,
    allowed_sucursal_keys,
    session: Any | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    active = session if session is not None else db.session
    if (
        type(campaign_id) is not int or campaign_id <= 0
        or type(page) is not int or page < 1
        or type(page_size) is not int or not 1 <= page_size <= 100
    ):
        raise ValidationError("Campaña o paginación inválidas.")
    rows = _ambiguous_rows(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys, session=active,
    )
    excluded = {
        int(row.recipient_id): str(row.reason)
        for row in active.query(MarketingCampaignV2RecipientDispatchExclusionORM)
        .filter(
            MarketingCampaignV2RecipientDispatchExclusionORM.campaign_id == campaign_id,
        ).all()
    }
    counts = Counter(row["kind"] for row in rows)
    candidates = [
        row["recipient_id"] for row in rows
        if row["kind"] == "AMBIGUOUS_EVIDENCE"
    ]
    conflicts = [
        rid for rid in candidates if rid in excluded
        and excluded[rid] != AMBIGUOUS_BRANCH_EVIDENCE
    ]
    effective = [rid for rid in candidates if rid not in excluded]
    payload = {
        "campaign_id": campaign_id,
        "review_fingerprint": _fingerprint(
            "AMBIGUOUS_BRANCH_EVIDENCE", campaign_id, candidates,
        ),
        "unresolved_count": len(rows),
        "counts": dict(sorted(counts.items())),
        "candidate_count": len(candidates),
        "already_excluded_count": sum(
            rid in excluded and excluded[rid] == AMBIGUOUS_BRANCH_EVIDENCE
            for rid in candidates
        ),
        "conflict_count": len(conflicts),
        "new_exclusions": len(effective),
        "requires_bulk_confirmation": len(effective) >= 10,
        "can_apply": bool(effective) and not conflicts,
        "page": page,
        "page_size": page_size,
        "rows": [
            {**row, "existing_exclusion_reason": excluded.get(row["recipient_id"])}
            for row in rows[(page - 1)*page_size:page*page_size]
        ],
    }
    return payload


def _lock_clean_target(*, campaign_id: int, allowed_sucursal_keys, session: Any):
    get_campaign_v2(
        campaign_id=campaign_id, allowed_sucursal_keys=allowed_sucursal_keys,
        session=session,
    )
    campaign = session.query(MarketingCampaignV2ORM).filter(
        MarketingCampaignV2ORM.id == campaign_id,
    ).with_for_update().one()
    if campaign.frozen_at is None:
        raise ValidationError("La campaña destino no está congelada.")
    if session.query(MarketingCampaignV2ProviderCampaignORM.id).filter(
        MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == campaign_id,
    ).first():
        raise ValidationError(
            "Campaña con provider children: no se permite cambiar exclusiones."
        )
    return campaign


def apply_ambiguous_branch_exclusions(
    *,
    campaign_id: int,
    expected_fingerprint: str,
    expected_count: int,
    actor_user_id: int,
    allow_bulk: bool,
    allowed_sucursal_keys,
    session: Any | None = None,
) -> dict[str, Any]:
    active = session if session is not None else db.session
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise ValidationError("Actor inválido.")
    if type(expected_count) is not int or expected_count <= 0:
        raise ValidationError("Confirma el total positivo de nuevos excluidos.")
    _lock_clean_target(
        campaign_id=campaign_id, allowed_sucursal_keys=allowed_sucursal_keys,
        session=active,
    )
    report = review_ambiguous_branches(
        campaign_id=campaign_id, allowed_sucursal_keys=allowed_sucursal_keys,
        session=active,
    )
    if (
        expected_fingerprint != report["review_fingerprint"]
        or expected_count != report["new_exclusions"]
        or not report["can_apply"]
    ):
        raise ValidationError("Revisión desactualizada o exclusiones en conflicto.")
    if expected_count >= 10 and allow_bulk is not True:
        raise ValidationError("10+ casos requieren confirmación masiva explícita.")
    if allow_bulk is not True and type(allow_bulk) is not bool:
        raise ValidationError("Confirmación inválida.")
    rows = _ambiguous_rows(
        campaign_id=campaign_id, allowed_sucursal_keys=allowed_sucursal_keys,
        session=active,
    )
    existing = {
        int(row.recipient_id) for row in
        active.query(MarketingCampaignV2RecipientDispatchExclusionORM)
        .filter(
            MarketingCampaignV2RecipientDispatchExclusionORM.campaign_id == campaign_id,
        ).all()
    }
    ids = [
        row["recipient_id"] for row in rows
        if row["kind"] == "AMBIGUOUS_EVIDENCE"
        and row["recipient_id"] not in existing
    ]
    if len(ids) != expected_count:
        raise ValidationError("Manifest cambió; vuelve a revisar.")
    staged = add_campaign_v2_ambiguous_branch_exclusions(
        campaign_id=campaign_id, recipient_ids=ids, actor_user_id=actor_user_id,
        allowed_sucursal_keys=allowed_sucursal_keys, session=active,
    )
    active.commit()
    return {**staged, "review_fingerprint": expected_fingerprint}


def _validate_sources(source_campaign_ids: Any, target_campaign_id: int) -> tuple[int, ...]:
    if (
        not isinstance(source_campaign_ids, list)
        or not 1 <= len(source_campaign_ids) <= 20
        or any(type(i) is not int or i <= 0 or i == target_campaign_id
               for i in source_campaign_ids)
        or len(set(source_campaign_ids)) != len(source_campaign_ids)
    ):
        raise ValidationError("Selecciona de 1 a 20 campañas origen distintas y válidas.")
    return tuple(sorted(source_campaign_ids))


def _previous_multi_proof(
    *, campaign_id: int, source_ids: tuple[int, ...],
    allowed_sucursal_keys, session: Any,
) -> dict[str, Any]:
    assignment: dict[int, int] = {}
    breakdown = []
    for source_id in source_ids:
        proof = find_previous_campaign_contact_ids(
            campaign_id=campaign_id, source_campaign_id=source_id,
            allowed_sucursal_keys=allowed_sucursal_keys, session=session,
        )
        new = 0
        for recipient_id in proof["matched_recipient_ids"]:
            if recipient_id not in assignment:
                assignment[recipient_id] = source_id
                new += 1
        breakdown.append({
            "source_campaign_id": source_id,
            "submitted_contacts": proof["source_submitted_phones_count"],
            "overlap_contacts": proof["matched"],
            "unique_assigned": new,
        })
    allocations = sorted(assignment.items())
    return {
        "campaign_id": campaign_id,
        "source_campaign_ids": list(source_ids),
        "matched": len(allocations),
        "source_breakdown": breakdown,
        "review_fingerprint": _fingerprint(
            "PREVIOUS_CAMPAIGN_CONTACT", campaign_id, allocations,
        ),
        "assignments": allocations,
    }


def review_previous_contacts(
    *,
    campaign_id: int, source_campaign_ids: Any, allowed_sucursal_keys,
    session: Any | None = None,
) -> dict[str, Any]:
    active = session if session is not None else db.session
    source_ids = _validate_sources(source_campaign_ids, campaign_id)
    proof = _previous_multi_proof(
        campaign_id=campaign_id, source_ids=source_ids,
        allowed_sucursal_keys=allowed_sucursal_keys, session=active,
    )
    existing = {
        int(r.recipient_id): r
        for r in active.query(MarketingCampaignV2RecipientDispatchExclusionORM)
        .filter(
            MarketingCampaignV2RecipientDispatchExclusionORM.campaign_id == campaign_id,
        ).all()
    }
    conflict = 0
    already = 0
    for rid, source_id in proof["assignments"]:
        prior = existing.get(rid)
        if prior is None:
            continue
        if prior.reason == PREVIOUS_CAMPAIGN_CONTACT:
            # Proven duplicate from an earlier source: preserve original
            # audit provenance; overlapping source IDs are not an error.
            already += 1
        else:
            conflict += 1
    return {
        **{key: val for key, val in proof.items() if key != "assignments"},
        "new_exclusions": proof["matched"] - conflict - already,
        "already_excluded_count": already,
        "conflict_count": conflict,
        "can_apply": proof["matched"] > 0 and conflict == 0,
    }


def apply_previous_contacts(
    *,
    campaign_id: int, source_campaign_ids: Any,
    expected_fingerprint: str, expected_count: int, actor_user_id: int,
    allow_bulk: bool, allowed_sucursal_keys, session: Any | None = None,
) -> dict[str, Any]:
    active = session if session is not None else db.session
    source_ids = _validate_sources(source_campaign_ids, campaign_id)
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise ValidationError("Actor inválido.")
    _lock_clean_target(
        campaign_id=campaign_id, allowed_sucursal_keys=allowed_sucursal_keys,
        session=active,
    )
    proof = _previous_multi_proof(
        campaign_id=campaign_id, source_ids=source_ids,
        allowed_sucursal_keys=allowed_sucursal_keys, session=active,
    )
    existing = {
        int(r.recipient_id): r
        for r in active.query(MarketingCampaignV2RecipientDispatchExclusionORM)
        .filter(
            MarketingCampaignV2RecipientDispatchExclusionORM.campaign_id == campaign_id,
        ).all()
    }
    new = [(rid, source_id) for rid, source_id in proof["assignments"]
           if rid not in existing]
    conflicts = [rid for rid, _source in proof["assignments"] if
                 rid in existing and existing[rid].reason != PREVIOUS_CAMPAIGN_CONTACT]
    if (
        expected_fingerprint != proof["review_fingerprint"]
        or type(expected_count) is not int or expected_count != len(new)
        or not new or conflicts
    ):
        raise ValidationError("Revisión desactualizada o exclusiones en conflicto.")
    if len(new) >= 10 and allow_bulk is not True:
        raise ValidationError("10+ contactos requieren confirmación masiva explícita.")
    if type(allow_bulk) is not bool:
        raise ValidationError("Confirmación inválida.")
    for recipient_id, source_id in new:
        active.add(MarketingCampaignV2RecipientDispatchExclusionORM(
            campaign_id=campaign_id, recipient_id=recipient_id,
            reason=PREVIOUS_CAMPAIGN_CONTACT, related_campaign_id=source_id,
            created_by_user_id=actor_user_id,
        ))
    active.flush()
    active.commit()
    return {
        "campaign_id": campaign_id,
        "added": len(new),
        "already_present": len(proof["assignments"]) - len(new),
        "source_breakdown": proof["source_breakdown"],
    }
