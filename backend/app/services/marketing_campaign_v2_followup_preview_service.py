"""Read-only OR preview for Campaign V2 follow-ups from one persisted snapshot.

This service never creates cohorts, changes contacts, calls a provider or sends.
Selected recipients are identified server-side, not supplied by the caller.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from sqlalchemy import and_

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ProviderRecipientObservationORM as Observation,
    MarketingCampaignV2ProviderStatsSnapshotORM as Snapshot,
    MarketingCampaignV2RecipientORM as Recipient,
)
from app.services.marketing_campaign_v2_query_service import (
    _load_visible_campaign_orm,
    _normalize_current_scope,
    _positive_int,
)

FOLLOWUP_PREVIEW_VERSION = "campaign-v2-followup-preview-or-v1"
FOLLOWUP_PROVIDER_STATUSES = frozenset({
    "VIEWED", "DELIVERED", "SENT", "FAILED",
    "SUCCESSFUL", "NO_PROVIDER_STATUS",
})


class FollowupPreviewValidationError(ValueError):
    """Malformed selection or client-supplied snapshot identity."""


class FollowupPreviewConflictError(RuntimeError):
    """A selected source snapshot changed or its recipient mapping is ambiguous."""


class FollowupPreviewUnavailableError(RuntimeError):
    """The source campaign does not have persisted provider observations yet."""


def _normalize_statuses(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise FollowupPreviewValidationError(
            "selected_statuses debe ser una lista no vacía de estados."
        )
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise FollowupPreviewValidationError("selected_statuses contiene estados inválidos.")
    normalized = tuple(sorted({item.strip().upper() for item in value}))
    if not set(normalized).issubset(FOLLOWUP_PROVIDER_STATUSES):
        raise FollowupPreviewValidationError(
            "Estados admitidos: VIEWED, DELIVERED, SENT, FAILED, "
            "SUCCESSFUL, NO_PROVIDER_STATUS. NO_SNAPSHOT no genera cohortes."
        )
    return normalized


def _status(outcome: str | None, bucket: str | None) -> str:
    if outcome == "FAILED":
        return "FAILED"
    if outcome == "SUCCESSFUL":
        return bucket if bucket in {"VIEWED", "DELIVERED", "SENT"} else "SUCCESSFUL"
    return "NO_PROVIDER_STATUS"


def build_followup_preview(
    *,
    source_campaign_id: Any,
    selected_statuses: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    expected_snapshot_id: Any = None,
    session=None,
) -> dict[str, Any]:
    """OR-union of recipients from the latest saved snapshot, scoped and immutable."""
    source_id = _positive_int(
        source_campaign_id, field_name="source_campaign_id", maximum=None,
    )
    statuses = _normalize_statuses(selected_statuses)
    requested_snapshot_id = (
        None if expected_snapshot_id is None else _positive_int(
            expected_snapshot_id, field_name="expected_snapshot_id", maximum=None,
        )
    )
    active = session if session is not None else db.session
    scope = _normalize_current_scope(allowed_sucursal_keys)

    with active.no_autoflush:
        # The same backend campaign visibility rule protects this preview.
        source = _load_visible_campaign_orm(
            campaign_id=source_id, scope=scope, session=active,
        )
        latest = (
            active.query(Snapshot)
            .filter(Snapshot.campaign_v2_id == source_id)
            .order_by(Snapshot.fetched_at.desc(), Snapshot.id.desc())
            .first()
        )
        if latest is None:
            raise FollowupPreviewUnavailableError(
                "La campaña no tiene un snapshot de estadísticas guardado."
            )
        if requested_snapshot_id is not None and latest.id != requested_snapshot_id:
            raise FollowupPreviewConflictError(
                "El snapshot cambió; vuelve a revisar los estados antes de continuar."
            )

        frozen_rows = (
            active.query(
                Recipient.id,
                Recipient.phone_mx10,
                Observation.id.label("observation_id"),
                Observation.normalized_phone,
                Observation.outcome,
                Observation.delivery_bucket,
            )
            .outerjoin(
                Observation,
                and_(
                    Observation.snapshot_id == latest.id,
                    Observation.campaign_recipient_id == Recipient.id,
                ),
            )
            .filter(Recipient.campaign_id == source_id)
            .order_by(Recipient.id.asc(), Observation.id.asc())
            .all()
        )

    counts = {key: 0 for key in sorted(FOLLOWUP_PROVIDER_STATUSES)}
    seen_ids: set[int] = set()
    identity_hash = hashlib.sha256()
    selected_count = 0
    for row in frozen_rows:
        recipient_id = int(row.id)
        if recipient_id in seen_ids:
            raise FollowupPreviewConflictError(
                "El snapshot tiene observaciones ambiguas para un destinatario."
            )
        seen_ids.add(recipient_id)
        if row.observation_id is not None and (
            row.normalized_phone != f"mx10:{row.phone_mx10}"
        ):
            raise FollowupPreviewConflictError(
                "La identidad congelada ya no coincide con la observación."
            )
        status = _status(row.outcome, row.delivery_bucket)
        counts[status] += 1
        if status in statuses:
            selected_count += 1
            # Internal integrity digest; no phones or recipient IDs leave the API.
            identity_hash.update(f"{recipient_id}:{row.phone_mx10}\n".encode("utf-8"))

    fingerprint_input = {
        "version": FOLLOWUP_PREVIEW_VERSION,
        "source_campaign_id": source_id,
        "snapshot_id": int(latest.id),
        "snapshot_fingerprint": latest.fingerprint,
        "selected_statuses": list(statuses),
        "candidate_count": selected_count,
        "candidate_identity_sha256": identity_hash.hexdigest(),
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_input, ensure_ascii=True, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "source_campaign_id": int(source.id),
        "source_campaign_name": source.name,
        "source_snapshot_id": int(latest.id),
        "source_snapshot_fetched_at": (
            latest.fetched_at.isoformat() if latest.fetched_at else None
        ),
        "source_snapshot_fingerprint": latest.fingerprint,
        "selected_statuses": list(statuses),
        "match_mode": "ANY",
        "source_recipient_count": len(seen_ids),
        "status_counts": counts,
        "candidate_count": selected_count,
        "preview_fingerprint_version": FOLLOWUP_PREVIEW_VERSION,
        "preview_fingerprint": fingerprint,
        "read_only": True,
        "campaign_created": False,
        "send_authorized": False,
        "sendable_count": None,
        "next_action": "REVIEW_AND_FREEZE_IN_SEPARATE_STEP",
    }
