"""Frontera provider-agnostic para lectura de estadísticas de campañas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class CampaignProviderCapabilities:
    campaign_stats: bool
    campaign_aggregate_analytics: bool
    recipient_status_buckets: bool
    recipient_button_interactions: bool
    recipient_response_attribution: bool
    recipient_event_timestamps: bool
    recipient_failure_causes: bool
    list_campaigns: bool
    send: bool


@dataclass(frozen=True)
class CampaignProviderRawCounts:
    successful: int
    failed: int
    sent: int
    delivered: int
    viewed: int
    answered: int
    interaction_groups: int
    interaction_items: int


@dataclass(frozen=True)
class CampaignProviderInteraction:
    label: str
    raw_item_count: int
    unique_recipient_phones: frozenset[str]


@dataclass(frozen=True)
class CampaignProviderStats:
    analytics_status: str | None
    analytics: Mapping[str, Any] | None
    raw_counts: CampaignProviderRawCounts
    successful_phones: frozenset[str]
    failed_phones: frozenset[str]
    sent_phones: frozenset[str]
    delivered_phones: frozenset[str]
    viewed_phones: frozenset[str]
    button_interactions: tuple[
        CampaignProviderInteraction,
        ...,
    ]


class CampaignProvider(Protocol):
    def capabilities(
        self,
    ) -> CampaignProviderCapabilities:
        ...

    def get_campaign_stats(
        self,
        provider_campaign_id: str,
    ) -> CampaignProviderStats:
        ...
