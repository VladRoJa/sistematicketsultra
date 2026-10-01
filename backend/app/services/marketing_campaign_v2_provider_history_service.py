"""Histórico provider recipient-level transversal para Campaign V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
)
from app.services.marketing_campaign_v2_query_service import (
    _campaign_visible_to_scope,
    _normalize_current_scope,
)
from app.services.marketing_iventas_service import normalize_iventas_phone


MAX_PROVIDER_HISTORY_PHONES = 100


class MarketingCampaignV2ProviderHistoryError(RuntimeError):
    """Base de errores M13."""


class MarketingCampaignV2ProviderHistoryValidationError(
    MarketingCampaignV2ProviderHistoryError,
    ValueError,
):
    """Input inválido para histórico provider."""


@dataclass(frozen=True)
class RecipientProviderCampaignObservation:
    campaign_v2_id: int
    provider: str
    provider_campaign_id: str
    snapshot_id: int
    observed_at: datetime
    outcome: str
    delivery_bucket: str | None
    button_labels: tuple[str, ...]


@dataclass(frozen=True)
class RecipientProviderHistory:
    normalized_phone: str
    campaign_count: int
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    observed_outcomes: tuple[str, ...]
    observed_delivery_buckets: tuple[str, ...]
    button_interacted: bool
    button_labels: tuple[str, ...]
    latest_by_campaign: tuple[RecipientProviderCampaignObservation, ...]


def get_provider_history_for_phones(
    *,
    phones: Iterable[Any],
    allowed_sucursal_keys: Iterable[str] | None,
    observed_before: datetime | None = None,
    session=None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_phones = _normalize_requested_phones(phones)
    cutoff = _normalize_cutoff(observed_before)
    scope = _normalize_current_scope(allowed_sucursal_keys)

    with active_session.no_autoflush:
        query = (
            active_session.query(
                MarketingCampaignV2ProviderRecipientObservationORM,
                MarketingCampaignV2ProviderStatsSnapshotORM,
                MarketingCampaignV2ORM,
            )
            .join(
                MarketingCampaignV2ProviderStatsSnapshotORM,
                MarketingCampaignV2ProviderStatsSnapshotORM.id
                == MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id,
            )
            .join(
                MarketingCampaignV2ORM,
                MarketingCampaignV2ORM.id
                == MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id,
            )
            .filter(
                MarketingCampaignV2ProviderRecipientObservationORM.normalized_phone.in_(
                    normalized_phones
                )
            )
        )
        if cutoff is not None:
            query = query.filter(
                MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at
                <= cutoff
            )

        db_rows = query.order_by(
            MarketingCampaignV2ProviderRecipientObservationORM.normalized_phone.asc(),
            MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.asc(),
            MarketingCampaignV2ProviderStatsSnapshotORM.id.asc(),
        ).all()

    visible_rows = [
        (observation, snapshot, campaign)
        for observation, snapshot, campaign in db_rows
        if _campaign_visible_to_scope(campaign, scope)
    ]

    rows_by_phone: dict[
        str,
        list[tuple[Any, Any, Any]],
    ] = {phone: [] for phone in normalized_phones}
    for observation, snapshot, campaign in visible_rows:
        rows_by_phone[observation.normalized_phone].append(
            (observation, snapshot, campaign)
        )

    histories = [
        _build_history(
            normalized_phone=phone,
            rows=rows_by_phone[phone],
        )
        for phone in normalized_phones
    ]

    return {
        "observed_before": _iso_datetime(cutoff),
        "phone_count": len(normalized_phones),
        "rows": [_serialize_history(history) for history in histories],
    }


def _build_history(
    *,
    normalized_phone: str,
    rows: list[tuple[Any, Any, Any]],
) -> RecipientProviderHistory:
    if not rows:
        return RecipientProviderHistory(
            normalized_phone=normalized_phone,
            campaign_count=0,
            first_observed_at=None,
            last_observed_at=None,
            observed_outcomes=(),
            observed_delivery_buckets=(),
            button_interacted=False,
            button_labels=(),
            latest_by_campaign=(),
        )

    outcomes: set[str] = set()
    delivery_buckets: set[str] = set()
    button_labels: set[str] = set()
    latest_by_campaign: dict[
        int,
        RecipientProviderCampaignObservation,
    ] = {}
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None

    for observation, snapshot, campaign in rows:
        observed_at = _as_utc(snapshot.fetched_at)
        outcomes.add(observation.outcome)
        if observation.delivery_bucket is not None:
            delivery_buckets.add(observation.delivery_bucket)
        labels = tuple(
            sorted(
                {
                    str(label)
                    for label in (observation.button_labels_json or [])
                }
            )
        )
        button_labels.update(labels)

        if (
            first_observed_at is None
            or observed_at < first_observed_at
        ):
            first_observed_at = observed_at
        if (
            last_observed_at is None
            or observed_at > last_observed_at
        ):
            last_observed_at = observed_at

        candidate = RecipientProviderCampaignObservation(
            campaign_v2_id=int(campaign.id),
            provider=snapshot.provider,
            provider_campaign_id=snapshot.provider_campaign_id,
            snapshot_id=int(snapshot.id),
            observed_at=observed_at,
            outcome=observation.outcome,
            delivery_bucket=observation.delivery_bucket,
            button_labels=labels,
        )
        current = latest_by_campaign.get(int(campaign.id))
        if current is None or (
            candidate.observed_at,
            candidate.snapshot_id,
        ) > (
            current.observed_at,
            current.snapshot_id,
        ):
            latest_by_campaign[int(campaign.id)] = candidate

    latest_rows = tuple(
        sorted(
            latest_by_campaign.values(),
            key=lambda item: (
                item.observed_at,
                item.snapshot_id,
                item.campaign_v2_id,
            ),
            reverse=True,
        )
    )

    return RecipientProviderHistory(
        normalized_phone=normalized_phone,
        campaign_count=len(latest_by_campaign),
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
        observed_outcomes=tuple(sorted(outcomes)),
        observed_delivery_buckets=tuple(sorted(delivery_buckets)),
        button_interacted=bool(button_labels),
        button_labels=tuple(sorted(button_labels)),
        latest_by_campaign=latest_rows,
    )


def _normalize_requested_phones(
    phones: Iterable[Any],
) -> tuple[str, ...]:
    if isinstance(phones, (str, bytes)) or phones is None:
        raise MarketingCampaignV2ProviderHistoryValidationError(
            "phones debe ser una lista de teléfonos."
        )

    try:
        raw_values = list(phones)
    except TypeError as exc:
        raise MarketingCampaignV2ProviderHistoryValidationError(
            "phones debe ser una lista de teléfonos."
        ) from exc

    if not raw_values:
        raise MarketingCampaignV2ProviderHistoryValidationError(
            "phones debe contener al menos un teléfono."
        )
    if len(raw_values) > MAX_PROVIDER_HISTORY_PHONES:
        raise MarketingCampaignV2ProviderHistoryValidationError(
            f"phones admite máximo {MAX_PROVIDER_HISTORY_PHONES} elementos."
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        internal = _normalize_history_phone(value)
        if internal not in seen:
            seen.add(internal)
            normalized.append(internal)

    return tuple(normalized)


def _normalize_history_phone(value: Any) -> str:
    if isinstance(value, str):
        clean = value.strip()
        if clean.startswith("mx10:"):
            suffix = clean[5:]
            if len(suffix) == 10 and suffix.isdigit():
                return clean

    phone = normalize_iventas_phone(value)
    if phone.phone_mx10 is None:
        raise MarketingCampaignV2ProviderHistoryValidationError(
            "Todos los teléfonos deben ser normalizables a MX10."
        )
    return f"mx10:{phone.phone_mx10}"


def _normalize_cutoff(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise MarketingCampaignV2ProviderHistoryValidationError(
            "observed_before debe ser datetime con zona horaria."
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise MarketingCampaignV2ProviderHistoryValidationError(
            "observed_before debe incluir zona horaria."
        )
    return value.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_history(
    history: RecipientProviderHistory,
) -> dict[str, Any]:
    return {
        "normalized_phone": history.normalized_phone,
        "campaign_count": history.campaign_count,
        "first_observed_at": _iso_datetime(
            history.first_observed_at
        ),
        "last_observed_at": _iso_datetime(
            history.last_observed_at
        ),
        "ever_observed": {
            "outcomes": list(history.observed_outcomes),
            "delivery_buckets": list(
                history.observed_delivery_buckets
            ),
            "button_interacted": history.button_interacted,
            "button_labels": list(history.button_labels),
        },
        "latest_by_campaign": [
            {
                "campaign_v2_id": item.campaign_v2_id,
                "provider": item.provider,
                "provider_campaign_id": item.provider_campaign_id,
                "snapshot_id": item.snapshot_id,
                "observed_at": _iso_datetime(item.observed_at),
                "outcome": item.outcome,
                "delivery_bucket": item.delivery_bucket,
                "button_labels": list(item.button_labels),
            }
            for item in history.latest_by_campaign
        ],
    }


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
