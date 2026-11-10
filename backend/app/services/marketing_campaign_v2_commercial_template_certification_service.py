"""Conservative, read-only template certification from actual commercial deliveries.

Uses existing iVentas child rows and immutable provider stats snapshots. No sends,
new schema, mutable certification flags or provider reads. Missing proof is NOT
certified. Snapshot observations must match a recipient of the exact child.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2ProviderCampaignORM as Child,
    MarketingCampaignV2ProviderStatsSnapshotORM as Snapshot,
    MarketingCampaignV2ProviderRecipientObservationORM as Observation,
)
from app.services.marketing_campaign_v2_confirmed_rejection import confirmed_rejected_child
from app.services.marketing_campaign_v2_dispatch_config_service import template_file_url
from app.services.marketing_phone import normalize_phone

DELIVERED = frozenset({"DELIVERED", "VIEWED"})


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _matching_child(child: Any, observation: Any, template: Any, *, channel: str,
                    binding_id: int, signature: str) -> bool:
    """Validate identity, immutable payload and current template version."""
    frozen = child.template_snapshot_json
    request = child.request_snapshot_json
    if not isinstance(frozen, dict) or not isinstance(request, dict):
        return False
    if (str(child.provider) != "IVENTAS" or child.status != "SUBMITTED"
            or not child.provider_campaign_id or not child.submitted_at
            or not child.submitted_by_user_id or int(child.recipient_count) <= 0
            or int(child.template_id) != int(template.id)
            or child.template_name != template.template_name
            or int(child.channel_binding_id) != int(binding_id)
            or str(child.provider_channel_id) != channel
            or frozen.get("template_id") != int(template.id)
            or frozen.get("template_name") != str(template.template_name)
            or frozen.get("file_url") != template_file_url(template)
            or request.get("provider") != "IVENTAS"
            or request.get("provider_channel_id") != channel
            or request.get("template_name") != template.template_name
            or request.get("file_url") != template_file_url(template)):
        return False
    if frozen.get("send_via_channel_binding_id") not in (None, binding_id):
        return False
    if frozen.get("send_via_provider_channel_id") not in (None, channel):
        return False

    # Future children carry the exact version hash. Historical children were
    # created without it, so require no template edits *at all* after sending.
    # This intentionally excludes uncertain legacy history rather than
    # claiming that variables still match.
    frozen_signature = frozen.get("certification_signature")
    if frozen_signature is not None:
        if frozen_signature != signature:
            return False
    else:
        modified = _utc(getattr(template, "updated_at", None))
        if modified is None or _utc(child.submitted_at) < modified:
            return False

    leads = request.get("leads")
    if (not isinstance(leads, list) or len(leads) != int(child.recipient_count)
            or getattr(observation, "campaign_recipient_id", None) is None
            or observation.outcome != "SUCCESSFUL"
            or observation.delivery_bucket not in DELIVERED):
        return False
    normalized = str(observation.normalized_phone or "")
    if not normalized.startswith("mx10:"):
        return False
    matched_phone = normalized[5:]
    return any(
        isinstance(lead, dict) and normalize_phone(lead.get("phone")) == matched_phone
        for lead in leads
    )


def last_confirmed_template_rejection(*, template_id: int, channel: str,
                                      session, after: datetime | None = None):
    """Latest deterministic TEMPLATE_NOT_FOUND for the exact template/channel."""
    query = (
        session.query(Child)
        .filter(
            Child.template_id == template_id,
            Child.provider == "IVENTAS",
            Child.provider_channel_id == channel,
            Child.status == "PROVIDER_ERROR",
            Child.error_code == "TEMPLATE_NOT_FOUND",
            Child.submit_started_at.isnot(None),
        )
        .order_by(Child.submit_started_at.desc(), Child.id.desc())
        .limit(20)
    )
    cutoff = _utc(after)
    for row in query.all():
        stamp = _utc(row.submit_started_at)
        if cutoff is not None and (stamp is None or stamp <= cutoff):
            continue
        if confirmed_rejected_child(row):
            return row
    return None


def commercial_certifications(*, template: Any, groups: dict, signature: str,
                              session, now: datetime | None = None) -> dict[str, dict]:
    """Return proven deliveries keyed by actual sending channel.

    Both historical and future captures are recognized without copying records
    or changing their audit data. A newer confirmed TEMPLATE_NOT_FOUND revokes
    an older successful delivery until another delivery proves recovery.
    """
    timestamp = _utc(now or datetime.now(timezone.utc))
    result: dict[str, dict] = {}
    for channel, group in groups.items():
        binding_id = int(group["binding_id"])
        candidates = (
            session.query(Child, Snapshot, Observation)
            .join(
                Snapshot,
                and_(
                    Snapshot.campaign_v2_id == Child.campaign_v2_id,
                    Snapshot.provider == Child.provider,
                    Snapshot.provider_campaign_id == Child.provider_campaign_id,
                ),
            )
            .join(Observation, Observation.snapshot_id == Snapshot.id)
            .join(Campaign, Campaign.id == Child.campaign_v2_id)
            .filter(
                Campaign.source != "QA_MANUAL",
                Child.provider == "IVENTAS",
                Child.template_id == int(template.id),
                Child.template_name == str(template.template_name),
                Child.provider_channel_id == channel,
                Child.channel_binding_id == binding_id,
                Child.status == "SUBMITTED",
                Child.provider_campaign_id.isnot(None),
                Child.submitted_at.isnot(None),
                Child.submitted_at <= timestamp,
                Child.recipient_count > 0,
                Snapshot.fetched_at >= Child.submitted_at,
                Snapshot.fetched_at <= timestamp,
                Observation.outcome == "SUCCESSFUL",
                Observation.delivery_bucket.in_(tuple(DELIVERED)),
                Observation.campaign_recipient_id.isnot(None),
            )
            .order_by(Child.submitted_at.desc(), Snapshot.fetched_at.desc())
            .limit(48)
            .all()
        )
        for child, snapshot, observation in candidates:
            if not _matching_child(child, observation, template, channel=channel,
                                   binding_id=binding_id, signature=signature):
                continue
            if last_confirmed_template_rejection(
                template_id=int(template.id), channel=channel,
                session=session, after=child.submitted_at,
            ) is not None:
                continue
            result[channel] = {
                "source": "COMMERCIAL_DELIVERY",
                "campaign_id": int(child.campaign_v2_id),
                "child_id": int(child.id),
                "provider_campaign_id": str(child.provider_campaign_id),
                "actor_user_id": child.submitted_by_user_id,
                "submitted_at": _utc(child.submitted_at).isoformat(),
                "observed_at": _utc(snapshot.fetched_at).isoformat(),
                "snapshot_id": int(snapshot.id),
                "delivery_status": (
                    "LEÍDA" if observation.delivery_bucket == "VIEWED" else "ENTREGADA"
                ),
            }
            break
    return result
