"""Adaptador M8 de iVentas hacia CampaignProvider."""

from __future__ import annotations

from app.integrations.iventas.campaigns_client import (
    IVentasCampaignsClient,
)
from app.services.marketing_campaign_iventas_stats_parser import (
    IVentasCampaignStats,
    parse_iventas_campaign_stats,
)
from app.services.marketing_campaign_provider import (
    CampaignProviderCapabilities,
    CampaignProviderInteraction,
    CampaignProviderRawCounts,
    CampaignProviderStats,
)


_IVENTAS_CAPABILITIES = CampaignProviderCapabilities(
    campaign_stats=True,
    campaign_aggregate_analytics=True,
    recipient_status_buckets=True,
    recipient_button_interactions=True,
    recipient_response_attribution=False,
    recipient_event_timestamps=False,
    recipient_failure_causes=False,
    list_campaigns=False,
    send=False,
)


class IVentasCampaignProvider:
    """Composición estricta client -> parser -> mapping interno."""

    def __init__(
        self,
        *,
        client: IVentasCampaignsClient,
    ) -> None:
        self._client = client
    def capabilities(
        self,
    ) -> CampaignProviderCapabilities:
        return _IVENTAS_CAPABILITIES

    def get_campaign_stats(
        self,
        provider_campaign_id: str,
    ) -> CampaignProviderStats:
        payload = self._client.get_campaign_stats(
            provider_campaign_id
        )
        parsed = parse_iventas_campaign_stats(
            payload
        )
        return self._map_stats(parsed)

    @staticmethod
    def _map_stats(
        parsed: IVentasCampaignStats,
    ) -> CampaignProviderStats:
        raw = parsed.raw_counts

        raw_counts = CampaignProviderRawCounts(
            successful=raw.successful,
            failed=raw.failed,
            sent=raw.sent,
            delivered=raw.delivered,
            viewed=raw.viewed,
            answered=raw.answered,
            interaction_groups=raw.interaction_groups,
            interaction_items=raw.interaction_items,
        )

        button_interactions = tuple(
            CampaignProviderInteraction(
                label=interaction.label,
                raw_item_count=interaction.raw_item_count,
                unique_recipient_phones=(
                    interaction.normalized_unique_phones
                ),
            )
            for interaction in parsed.interactions
        )
        return CampaignProviderStats(
            analytics_status=parsed.analytics_status,
            analytics=parsed.analytics,
            raw_counts=raw_counts,
            successful_phones=parsed.successful_phones,
            failed_phones=parsed.failed_phones,
            sent_phones=parsed.sent_phones,
            delivered_phones=parsed.delivered_phones,
            viewed_phones=parsed.viewed_phones,
            button_interactions=button_interactions,
        )
