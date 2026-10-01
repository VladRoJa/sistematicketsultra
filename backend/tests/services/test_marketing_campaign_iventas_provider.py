import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.integrations.iventas.campaigns_client import (
    IVentasCampaignsProviderError,
)
from app.services.marketing_campaign_iventas_provider import (
    IVentasCampaignProvider,
)
from app.services.marketing_campaign_iventas_stats_parser import (
    IVentasCampaignStatsInvariantError,
)


class FakeClient:
    def __init__(
        self,
        *,
        payload=None,
        error=None,
    ):
        self.payload = payload
        self.error = error
        self.calls = []

    def get_campaign_stats(
        self,
        campaign_id,
    ):
        self.calls.append(campaign_id)
        if self.error is not None:
            raise self.error
        return self.payload


FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "iventas_campaign_stats_observed_sanitized.json"
)

with FIXTURE_PATH.open(
    "r",
    encoding="utf-8",
) as fixture_file:
    _BASE_PAYLOAD = json.load(fixture_file)


def _payload(
    *,
    analytics_status="ok",
    analytics=None,
):
    payload = deepcopy(_BASE_PAYLOAD)
    payload["analyticsStatus"] = analytics_status

    if analytics is not None:
        payload["analytics"] = analytics

    return payload
def test_capabilities_are_exact_for_m8():
    provider = IVentasCampaignProvider(
        client=FakeClient(payload=_payload()),
    )

    capabilities = provider.capabilities()

    assert capabilities.campaign_stats is True
    assert capabilities.campaign_aggregate_analytics is True
    assert capabilities.recipient_status_buckets is True
    assert capabilities.recipient_button_interactions is True
    assert capabilities.recipient_response_attribution is False
    assert capabilities.recipient_event_timestamps is False
    assert capabilities.recipient_failure_causes is False
    assert capabilities.list_campaigns is False
    assert capabilities.send is False


def test_provider_composes_client_parser_and_mapping():
    client = FakeClient(
        payload=_payload(),
    )
    provider = IVentasCampaignProvider(
        client=client,
    )

    stats = provider.get_campaign_stats(
        "provider-campaign-123"
    )

    assert client.calls == [
        "provider-campaign-123",
    ]
    assert stats.raw_counts.successful == 3
    assert stats.raw_counts.failed == 1
    assert stats.raw_counts.sent == 1
    assert stats.raw_counts.delivered == 1
    assert stats.raw_counts.viewed == 1
    assert stats.raw_counts.answered == 0
    assert stats.raw_counts.interaction_groups == 1
    assert stats.raw_counts.interaction_items == 2

    assert stats.successful_phones == frozenset({
        "mx10:6861111111",
        "mx10:6862222222",
        "mx10:6863333333",
    })
    assert stats.failed_phones == frozenset({
        "mx10:6864444444",
    })
    assert stats.sent_phones == frozenset({
        "mx10:6861111111",
    })
    assert stats.delivered_phones == frozenset({
        "mx10:6862222222",
    })
    assert stats.viewed_phones == frozenset({
        "mx10:6863333333",
    })


def test_button_interactions_map_mechanically():
    provider = IVentasCampaignProvider(
        client=FakeClient(payload=_payload()),
    )

    stats = provider.get_campaign_stats("abc")
    assert len(stats.button_interactions) == 1
    interaction = stats.button_interactions[0]
    assert interaction.label == "Me interesa"
    assert interaction.raw_item_count == 2
    assert interaction.unique_recipient_phones == frozenset({
        "mx10:6863333333",
    })
    assert not hasattr(stats, "interactions")
    assert not hasattr(stats, "responded_phones")
    assert not hasattr(stats, "failure_reason_by_phone")
    assert not hasattr(stats, "sent_at")
    assert not hasattr(stats, "delivered_at")
    assert not hasattr(stats, "viewed_at")


def test_analytics_crosses_as_opaque_aggregate():
    analytics = {
        "responders": 79,
        "interactions": {
            "campaignButton": 63,
            "freeText": 16,
        },
        "providerSpecific": {
            "futureField": True,
        },
    }
    provider = IVentasCampaignProvider(
        client=FakeClient(
            payload=_payload(
                analytics=analytics,
            )
        ),
    )

    stats = provider.get_campaign_stats("abc")

    assert stats.analytics_status == "ok"
    assert stats.analytics == analytics
    assert not hasattr(stats, "responded_phones")
def test_not_synced_and_absent_analytics_cross_frontier():
    payload = _payload(
        analytics_status="not_synced",
        analytics={},
    )
    payload.pop("analytics")

    provider = IVentasCampaignProvider(
        client=FakeClient(payload=payload),
    )

    stats = provider.get_campaign_stats("abc")

    assert stats.analytics_status == "not_synced"
    assert stats.analytics is None
    assert len(stats.successful_phones) == 3


def test_client_error_propagates_unchanged():
    error = IVentasCampaignsProviderError(
        status_code=429,
        provider_code="RATE_LIMIT",
        support_ref=None,
        retryable=True,
        retry_after_seconds=120.0,
    )
    provider = IVentasCampaignProvider(
        client=FakeClient(error=error),
    )

    with pytest.raises(
        IVentasCampaignsProviderError
    ) as exc_info:
        provider.get_campaign_stats("abc")

    assert exc_info.value is error


def test_parser_error_propagates_unchanged_type():
    payload = _payload()
    payload["deliveredMessages"] = [
        "+52 686 111 1111",
    ]

    provider = IVentasCampaignProvider(
        client=FakeClient(payload=payload),
    )

    with pytest.raises(
        IVentasCampaignStatsInvariantError,
        match="sent/delivered",
    ):
        provider.get_campaign_stats("abc")


def test_provider_does_not_expose_legacy_sentd_count():
    provider = IVentasCampaignProvider(
        client=FakeClient(payload=_payload()),
    )

    stats = provider.get_campaign_stats("abc")

    assert not hasattr(
        stats.raw_counts,
        "sentd",
    )
