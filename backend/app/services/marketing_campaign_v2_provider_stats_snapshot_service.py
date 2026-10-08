"""Snapshots append-only de provider stats para Campaign V2."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_provider import CampaignProviderStats
from app.services.marketing_campaign_v2_provider_stats_service import (
    ProviderResolver,
    fetch_campaign_v2_provider_stats,
)
from app.services.marketing_campaign_provider_registry import (
    resolve_campaign_provider,
)
from app.services.marketing_campaign_v2_query_service import (
    _load_visible_campaign_orm,
    _normalize_current_scope,
    _positive_int,
)


class MarketingCampaignV2ProviderStatsSnapshotError(RuntimeError):
    pass


class MarketingCampaignV2ProviderStatsSnapshotPersistenceError(
    MarketingCampaignV2ProviderStatsSnapshotError
):
    pass


def capture_campaign_v2_provider_stats_snapshot(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    provider_campaign_child_id: Any | None = None,
    session=None,
    provider_resolver: ProviderResolver = resolve_campaign_provider,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    fetched = fetch_campaign_v2_provider_stats(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        provider_campaign_child_id=provider_campaign_child_id,
        session=active_session,
        provider_resolver=provider_resolver,
    )
    fetched_at = _normalize_now(now)
    fingerprint = fingerprint_campaign_provider_stats(fetched.stats)

    existing = _find_snapshot(
        session=active_session,
        campaign_id=fetched.campaign_id,
        provider=fetched.provider,
        provider_campaign_id=fetched.provider_campaign_id,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return _serialize_snapshot(existing, created=False)

    frozen_rows = (
        active_session.query(
            MarketingCampaignV2RecipientORM.id,
            MarketingCampaignV2RecipientORM.phone_mx10,
        )
        .filter(
            MarketingCampaignV2RecipientORM.campaign_id
            == fetched.campaign_id
        )
        .all()
    )
    frozen_by_phone = {
        row.phone_mx10: int(row.id)
        for row in frozen_rows
    }
    observation_specs = _build_observation_specs(
        fetched.stats,
        frozen_by_phone=frozen_by_phone,
    )
    matched_ids = {
        item["campaign_recipient_id"]
        for item in observation_specs
        if item["campaign_recipient_id"] is not None
    }
    provider_count = len(observation_specs)
    matched_count = len(matched_ids)

    raw = fetched.stats.raw_counts
    snapshot = MarketingCampaignV2ProviderStatsSnapshotORM(
        campaign_v2_id=fetched.campaign_id,
        provider_campaign_child_id=fetched.provider_campaign_child_id,
        provider=fetched.provider,
        provider_campaign_id=fetched.provider_campaign_id,
        analytics_status=fetched.stats.analytics_status,
        fetched_at=fetched_at,
        raw_successful=raw.successful,
        raw_failed=raw.failed,
        raw_sent=raw.sent,
        raw_delivered=raw.delivered,
        raw_viewed=raw.viewed,
        raw_answered=raw.answered,
        raw_interaction_groups=raw.interaction_groups,
        raw_interaction_items=raw.interaction_items,
        analytics_json=(
            deepcopy(dict(fetched.stats.analytics))
            if fetched.stats.analytics is not None
            else None
        ),
        button_interactions_json=_canonical_button_interactions(
            fetched.stats
        ),
        provider_recipient_count=provider_count,
        matched_recipient_count=matched_count,
        unmatched_provider_count=provider_count - matched_count,
        frozen_recipient_without_provider_status_count=(
            len(frozen_by_phone) - matched_count
        ),
        fingerprint=fingerprint,
        created_at=fetched_at,
    )
    active_session.add(snapshot)

    try:
        active_session.flush()
        for item in observation_specs:
            active_session.add(
                MarketingCampaignV2ProviderRecipientObservationORM(
                    snapshot_id=snapshot.id,
                    normalized_phone=item["normalized_phone"],
                    campaign_recipient_id=item["campaign_recipient_id"],
                    outcome=item["outcome"],
                    delivery_bucket=item["delivery_bucket"],
                    button_labels_json=item["button_labels"],
                    created_at=fetched_at,
                )
            )
        active_session.commit()
    except IntegrityError as exc:
        active_session.rollback()
        existing = _find_snapshot(
            session=active_session,
            campaign_id=fetched.campaign_id,
            provider=fetched.provider,
            provider_campaign_id=fetched.provider_campaign_id,
            fingerprint=fingerprint,
        )
        if existing is not None:
            return _serialize_snapshot(existing, created=False)
        raise MarketingCampaignV2ProviderStatsSnapshotPersistenceError(
            "Conflicto al persistir snapshot provider stats."
        ) from exc
    except SQLAlchemyError as exc:
        active_session.rollback()
        raise MarketingCampaignV2ProviderStatsSnapshotPersistenceError(
            "No fue posible persistir snapshot provider stats."
        ) from exc

    return _serialize_snapshot(snapshot, created=True)


def list_campaign_v2_provider_stats_snapshots(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_id = _visible_campaign_id(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=active_session,
    )
    with active_session.no_autoflush:
        rows = (
            active_session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
            .filter(
                MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id
                == normalized_id
            )
            .order_by(
                MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.desc(),
                MarketingCampaignV2ProviderStatsSnapshotORM.id.desc(),
            )
            .all()
        )
        serialized = [
            _serialize_snapshot(row, created=False)
            for row in rows
        ]
    return {
        "campaign_id": normalized_id,
        "rows": serialized,
    }


def get_latest_campaign_v2_provider_stats_snapshot(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
) -> dict[str, Any] | None:
    active_session = session if session is not None else db.session
    normalized_id = _visible_campaign_id(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=active_session,
    )
    with active_session.no_autoflush:
        row = (
            active_session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
            .filter(
                MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id
                == normalized_id
            )
            .order_by(
                MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.desc(),
                MarketingCampaignV2ProviderStatsSnapshotORM.id.desc(),
            )
            .first()
        )
        return (
            None
            if row is None
            else _serialize_snapshot(row, created=False)
        )


def fingerprint_campaign_provider_stats(stats: CampaignProviderStats) -> str:
    canonical = {
        "analytics_status": stats.analytics_status,
        "raw_counts": {
            "successful": stats.raw_counts.successful,
            "failed": stats.raw_counts.failed,
            "sent": stats.raw_counts.sent,
            "delivered": stats.raw_counts.delivered,
            "viewed": stats.raw_counts.viewed,
            "answered": stats.raw_counts.answered,
            "interaction_groups": stats.raw_counts.interaction_groups,
            "interaction_items": stats.raw_counts.interaction_items,
        },
        "recipients": {
            "successful": sorted(stats.successful_phones),
            "failed": sorted(stats.failed_phones),
            "sent": sorted(stats.sent_phones),
            "delivered": sorted(stats.delivered_phones),
            "viewed": sorted(stats.viewed_phones),
        },
        "button_interactions": _canonical_button_interactions(stats),
        "analytics": (
            deepcopy(dict(stats.analytics))
            if stats.analytics is not None
            else None
        ),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_button_interactions(stats: CampaignProviderStats) -> list[dict[str, Any]]:
    rows = [
        {
            "label": item.label,
            "raw_item_count": item.raw_item_count,
            "recipient_phones": sorted(item.unique_recipient_phones),
        }
        for item in stats.button_interactions
    ]
    return sorted(
        rows,
        key=lambda row: (
            row["label"],
            row["raw_item_count"],
            tuple(row["recipient_phones"]),
        ),
    )


def _build_observation_specs(
    stats: CampaignProviderStats,
    *,
    frozen_by_phone: dict[str, int],
) -> list[dict[str, Any]]:
    button_labels: dict[str, set[str]] = {}
    for interaction in stats.button_interactions:
        for phone in interaction.unique_recipient_phones:
            button_labels.setdefault(phone, set()).add(interaction.label)

    delivery_by_phone: dict[str, str] = {}
    for bucket, phones in (
        ("SENT", stats.sent_phones),
        ("DELIVERED", stats.delivered_phones),
        ("VIEWED", stats.viewed_phones),
    ):
        for phone in phones:
            delivery_by_phone[phone] = bucket

    rows = []
    for phone in sorted(stats.successful_phones | stats.failed_phones):
        outcome = "FAILED" if phone in stats.failed_phones else "SUCCESSFUL"
        mx10 = _mx10_from_normalized_phone(phone)
        rows.append(
            {
                "normalized_phone": phone,
                "campaign_recipient_id": (
                    frozen_by_phone.get(mx10)
                    if mx10 is not None
                    else None
                ),
                "outcome": outcome,
                "delivery_bucket": (
                    None
                    if outcome == "FAILED"
                    else delivery_by_phone.get(phone)
                ),
                "button_labels": sorted(button_labels.get(phone, set())),
            }
        )
    return rows


def _mx10_from_normalized_phone(value: str) -> str | None:
    prefix = "mx10:"
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    phone = value[len(prefix):]
    if len(phone) != 10 or not phone.isdigit():
        return None
    return phone


def _find_snapshot(
    *,
    session,
    campaign_id: int,
    provider: str,
    provider_campaign_id: str,
    fingerprint: str,
):
    return (
        session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
        .filter(
            MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id
            == campaign_id,
            MarketingCampaignV2ProviderStatsSnapshotORM.provider == provider,
            MarketingCampaignV2ProviderStatsSnapshotORM.provider_campaign_id
            == provider_campaign_id,
            MarketingCampaignV2ProviderStatsSnapshotORM.fingerprint
            == fingerprint,
        )
        .first()
    )


def _visible_campaign_id(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session,
) -> int:
    normalized_id = _positive_int(
        campaign_id,
        field_name="campaign_id",
        maximum=None,
    )
    scope = _normalize_current_scope(allowed_sucursal_keys)
    with session.no_autoflush:
        campaign = _load_visible_campaign_orm(
            campaign_id=normalized_id,
            scope=scope,
            session=session,
        )
    return int(campaign.id)


def _serialize_snapshot(snapshot, *, created: bool) -> dict[str, Any]:
    observations = sorted(
        snapshot.observations,
        key=lambda row: (row.normalized_phone, row.id or 0),
    )
    return {
        "id": int(snapshot.id),
        "campaign_id": int(snapshot.campaign_v2_id),
        "provider": snapshot.provider,
        "provider_campaign_id": snapshot.provider_campaign_id,
        "provider_campaign_child_id": snapshot.provider_campaign_child_id,
        "analytics_status": snapshot.analytics_status,
        "fetched_at": _iso_datetime(snapshot.fetched_at),
        "created_at": _iso_datetime(snapshot.created_at),
        "fingerprint": snapshot.fingerprint,
        "created": bool(created),
        "raw_counts": {
            "successful": snapshot.raw_successful,
            "failed": snapshot.raw_failed,
            "sent": snapshot.raw_sent,
            "delivered": snapshot.raw_delivered,
            "viewed": snapshot.raw_viewed,
            "answered": snapshot.raw_answered,
            "interaction_groups": snapshot.raw_interaction_groups,
            "interaction_items": snapshot.raw_interaction_items,
        },
        "diagnostics": {
            "provider_recipient_count": snapshot.provider_recipient_count,
            "matched_recipient_count": snapshot.matched_recipient_count,
            "unmatched_provider_count": snapshot.unmatched_provider_count,
            "frozen_recipient_without_provider_status_count": (
                snapshot.frozen_recipient_without_provider_status_count
            ),
        },
        "button_interactions": deepcopy(
            snapshot.button_interactions_json or []
        ),
        "analytics": (
            deepcopy(snapshot.analytics_json)
            if snapshot.analytics_json is not None
            else None
        ),
        "observations": [
            {
                "normalized_phone": row.normalized_phone,
                "campaign_recipient_id": row.campaign_recipient_id,
                "outcome": row.outcome,
                "delivery_bucket": row.delivery_bucket,
                "button_labels": list(row.button_labels_json or []),
            }
            for row in observations
        ],
    }


def _normalize_now(value: datetime | None) -> datetime:
    now = value if value is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
