"""Reporting individual offline/read-only para Campaign V2."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from numbers import Real
from typing import Any, Iterable, Mapping

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_query_service import (
    _extract_frozen_scope,
    _load_visible_campaign_orm,
    _normalize_current_scope,
    _positive_int,
)
from app.services.marketing_campaign_v2_reporting_cost_service import (
    extract_campaign_cost_projection,
)


_UNKNOWN_DIMENSION = "UNKNOWN"
_SUCCESSFUL = "SUCCESSFUL"
_FAILED = "FAILED"
_SENT = "SENT"
_DELIVERED = "DELIVERED"
_VIEWED = "VIEWED"


def build_campaign_v2_individual_report(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
) -> dict[str, Any]:
    """Construye un reporte reproducible sólo desde persistencia Suite."""
    active_session = session if session is not None else db.session
    normalized_id = _positive_int(
        campaign_id,
        field_name="campaign_id",
        maximum=None,
    )
    current_scope = _normalize_current_scope(allowed_sucursal_keys)

    with active_session.no_autoflush:
        campaign = _load_visible_campaign_orm(
            campaign_id=normalized_id,
            scope=current_scope,
            session=active_session,
        )

        recipients = (
            active_session.query(MarketingCampaignV2RecipientORM)
            .filter(
                MarketingCampaignV2RecipientORM.campaign_id
                == normalized_id
            )
            .order_by(MarketingCampaignV2RecipientORM.id.asc())
            .all()
        )
        recipient_ids = [int(row.id) for row in recipients]

        evidence_rows = []
        if recipient_ids:
            evidence_rows = (
                active_session.query(MarketingCampaignV2RecipientEvidenceORM)
                .filter(
                    MarketingCampaignV2RecipientEvidenceORM.recipient_id.in_(
                        recipient_ids
                    )
                )
                .order_by(
                    MarketingCampaignV2RecipientEvidenceORM.recipient_id.asc(),
                    MarketingCampaignV2RecipientEvidenceORM.evidence_order.asc(),
                    MarketingCampaignV2RecipientEvidenceORM.id.asc(),
                )
                .all()
            )

        snapshots = (
            active_session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
            .filter(
                MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id
                == normalized_id
            )
            .order_by(
                MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.asc(),
                MarketingCampaignV2ProviderStatsSnapshotORM.id.asc(),
            )
            .all()
        )
        snapshot_ids = [int(row.id) for row in snapshots]

        observation_rows = []
        if snapshot_ids:
            observation_rows = (
                active_session.query(
                    MarketingCampaignV2ProviderRecipientObservationORM
                )
                .filter(
                    MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.in_(
                        snapshot_ids
                    )
                )
                .order_by(
                    MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.asc(),
                    MarketingCampaignV2ProviderRecipientObservationORM.id.asc(),
                )
                .all()
            )

    observations_by_snapshot: dict[int, list[Any]] = defaultdict(list)
    for row in observation_rows:
        observations_by_snapshot[int(row.snapshot_id)].append(row)

    latest_snapshot = snapshots[-1] if snapshots else None
    latest_observations = (
        observations_by_snapshot[int(latest_snapshot.id)]
        if latest_snapshot is not None
        else []
    )
    total_recipients = len(recipients)
    normalized = _normalized_metrics(latest_observations)
    rates = _rates(
        total_recipients=total_recipients,
        normalized=normalized,
    )
    coverage = _coverage(
        snapshot=latest_snapshot,
        total_recipients=total_recipients,
    )
    interactions = _interactions(
        snapshot=latest_snapshot,
        observations=latest_observations,
    )
    analytics = (
        latest_snapshot.analytics_json
        if latest_snapshot is not None
        else None
    )

    return {
        "campaign": {
            "id": int(campaign.id),
            "name": campaign.name,
            "purpose": campaign.purpose,
            "source": campaign.source,
            "provider": campaign.provider,
            "provider_campaign_id": campaign.provider_campaign_id,
            "frozen_at": _iso_datetime(campaign.frozen_at),
        },
        "observation": {
            "snapshot_id": (
                int(latest_snapshot.id)
                if latest_snapshot is not None
                else None
            ),
            "latest_observed_at": (
                _iso_datetime(latest_snapshot.fetched_at)
                if latest_snapshot is not None
                else None
            ),
            "analytics_status": (
                latest_snapshot.analytics_status
                if latest_snapshot is not None
                else None
            ),
            "fingerprint": (
                latest_snapshot.fingerprint
                if latest_snapshot is not None
                else None
            ),
        },
        "audience": {
            "total_recipients": total_recipients,
        },
        "normalized": normalized,
        "rates": rates,
        "coverage": coverage,
        "provider_raw": _provider_raw(latest_snapshot),
        "interactions": {
            **interactions,
            "responders_aggregate": _analytics_number(
                analytics,
                "responders",
            ),
            "free_text_aggregate": _analytics_number(
                analytics,
                "interactions",
                "freeText",
            ),
        },
        "cost": extract_campaign_cost_projection(analytics),
        "dimensions": _dimensions(
            campaign=campaign,
            recipients=recipients,
            evidence_rows=evidence_rows,
        ),
        "evolution": [
            _evolution_point(
                snapshot=snapshot,
                observations=observations_by_snapshot[int(snapshot.id)],
            )
            for snapshot in snapshots
        ],
    }


def _normalized_metrics(observations: Iterable[Any]) -> dict[str, int]:
    successful: set[int] = set()
    failed: set[int] = set()
    sent: set[int] = set()
    delivered: set[int] = set()
    viewed: set[int] = set()

    for row in observations:
        recipient_id = getattr(row, "campaign_recipient_id", None)
        if recipient_id is None:
            continue
        recipient_id = int(recipient_id)
        outcome = str(getattr(row, "outcome", "") or "").upper()
        delivery = str(
            getattr(row, "delivery_bucket", "") or ""
        ).upper()

        if outcome == _FAILED:
            failed.add(recipient_id)
            continue
        if outcome != _SUCCESSFUL:
            continue

        successful.add(recipient_id)
        if delivery == _SENT:
            sent.add(recipient_id)
        elif delivery == _DELIVERED:
            delivered.add(recipient_id)
        elif delivery == _VIEWED:
            viewed.add(recipient_id)

    reach = delivered | viewed
    return {
        "successful": len(successful),
        "failed": len(failed),
        "sent": len(sent),
        "delivered": len(delivered),
        "viewed": len(viewed),
        "reach_count": len(reach),
    }


def _rates(
    *,
    total_recipients: int,
    normalized: Mapping[str, int],
) -> dict[str, float | None]:
    reach_count = int(normalized["reach_count"])
    return {
        "successful_rate": _safe_rate(
            int(normalized["successful"]),
            total_recipients,
        ),
        "reach_rate": _safe_rate(
            reach_count,
            total_recipients,
        ),
        "read_rate": _safe_rate(
            int(normalized["viewed"]),
            reach_count,
        ),
        "failure_rate": _safe_rate(
            int(normalized["failed"]),
            total_recipients,
        ),
    }


def _coverage(
    *,
    snapshot: Any | None,
    total_recipients: int,
) -> dict[str, int | float | None]:
    if snapshot is None:
        matched = 0
        unmatched = 0
        without_status = total_recipients
    else:
        matched = int(snapshot.matched_recipient_count)
        unmatched = int(snapshot.unmatched_provider_count)
        without_status = int(
            snapshot.frozen_recipient_without_provider_status_count
        )
    return {
        "matched_recipient_count": matched,
        "unmatched_provider_count": unmatched,
        "frozen_recipient_without_provider_status_count": without_status,
        "status_coverage_rate": _safe_rate(
            matched,
            total_recipients,
        ),
    }


def _provider_raw(snapshot: Any | None) -> dict[str, int] | None:
    if snapshot is None:
        return None
    return {
        "successful": int(snapshot.raw_successful),
        "failed": int(snapshot.raw_failed),
        "sent": int(snapshot.raw_sent),
        "delivered": int(snapshot.raw_delivered),
        "viewed": int(snapshot.raw_viewed),
        "answered": int(snapshot.raw_answered),
        "interaction_groups": int(snapshot.raw_interaction_groups),
        "interaction_items": int(snapshot.raw_interaction_items),
    }


def _interactions(
    *,
    snapshot: Any | None,
    observations: Iterable[Any],
) -> dict[str, Any]:
    recipients_by_label: dict[str, set[int]] = defaultdict(set)
    unique_button_recipients: set[int] = set()

    for row in observations:
        recipient_id = getattr(row, "campaign_recipient_id", None)
        if recipient_id is None:
            continue
        labels = _string_labels(
            getattr(row, "button_labels_json", None)
        )
        if not labels:
            continue
        recipient_id = int(recipient_id)
        unique_button_recipients.add(recipient_id)
        for label in labels:
            recipients_by_label[label].add(recipient_id)

    raw_items_by_label: dict[str, int] = {}
    if snapshot is not None:
        payload = snapshot.button_interactions_json
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, Mapping):
                    continue
                label = _clean_string(item.get("label"))
                raw_item_count = item.get("raw_item_count")
                if (
                    label is not None
                    and _is_nonnegative_int(raw_item_count)
                ):
                    raw_items_by_label[label] = (
                        raw_items_by_label.get(label, 0)
                        + int(raw_item_count)
                    )

    labels = sorted(
        set(recipients_by_label) | set(raw_items_by_label)
    )
    return {
        "unique_button_recipients": len(unique_button_recipients),
        "button_groups": [
            {
                "label": label,
                "unique_recipient_count": len(
                    recipients_by_label.get(label, set())
                ),
                "raw_item_count": raw_items_by_label.get(label),
            }
            for label in labels
        ],
    }


def _dimensions(
    *,
    campaign: Any,
    recipients: list[Any],
    evidence_rows: list[Any],
) -> dict[str, Any]:
    evidence_by_recipient: dict[int, list[Any]] = defaultdict(list)
    for row in evidence_rows:
        evidence_by_recipient[int(row.recipient_id)].append(row)

    branch_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()

    for recipient in recipients:
        evidence = evidence_by_recipient.get(int(recipient.id), [])
        branch_counts[
            _recipient_dimension(
                getattr(recipient, "sucursal", None),
                [
                    getattr(row, "sucursal_key", None)
                    or getattr(row, "sucursal", None)
                    for row in evidence
                ],
            )
        ] += 1
        family_counts[
            _recipient_dimension(
                getattr(recipient, "audience_family", None),
                [
                    getattr(row, "audience_family", None)
                    for row in evidence
                ],
            )
        ] += 1

    frozen_scope = _extract_frozen_scope(campaign)
    return {
        "scope": {
            "is_global": frozen_scope is None,
            "allowed_sucursal_keys": (
                None
                if frozen_scope is None
                else list(frozen_scope)
            ),
        },
        "branches": _dimension_rows(branch_counts),
        "audience_families": _dimension_rows(family_counts),
    }


def _recipient_dimension(
    primary: Any,
    evidence_values: Iterable[Any],
) -> str:
    primary_value = _clean_string(primary)
    if primary_value is not None:
        return primary_value

    values = {
        value
        for value in (
            _clean_string(raw)
            for raw in evidence_values
        )
        if value is not None
    }
    if len(values) == 1:
        return next(iter(values))
    return _UNKNOWN_DIMENSION


def _dimension_rows(counts: Counter[str]) -> list[dict[str, Any]]:
    return [
        {
            "value": value,
            "recipient_count": int(count),
        }
        for value, count in sorted(counts.items())
    ]


def _evolution_point(
    *,
    snapshot: Any,
    observations: Iterable[Any],
) -> dict[str, Any]:
    return {
        "snapshot_id": int(snapshot.id),
        "observed_at": _iso_datetime(snapshot.fetched_at),
        "normalized": _normalized_metrics(observations),
        "provider_raw": {
            "successful": int(snapshot.raw_successful),
            "failed": int(snapshot.raw_failed),
            "sent": int(snapshot.raw_sent),
            "delivered": int(snapshot.raw_delivered),
            "viewed": int(snapshot.raw_viewed),
        },
        "coverage": {
            "matched_recipient_count": int(
                snapshot.matched_recipient_count
            ),
            "unmatched_provider_count": int(
                snapshot.unmatched_provider_count
            ),
        },
    }


def _analytics_number(
    analytics: Any,
    *path: str,
) -> int | float | None:
    current = analytics
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    if isinstance(current, bool) or not isinstance(current, Real):
        return None
    return current


def _safe_rate(
    numerator: int,
    denominator: int,
) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _string_labels(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        sorted(
            {
                label
                for label in (
                    _clean_string(item)
                    for item in value
                )
                if label is not None
            }
        )
    )


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _is_nonnegative_int(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat()
