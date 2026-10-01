import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.marketing_campaign_iventas_stats_parser import (
    IVentasCampaignStatsInvariantError,
    IVentasCampaignStatsPayloadError,
    parse_iventas_campaign_stats,
)


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


def _payload() -> dict:
    return deepcopy(_BASE_PAYLOAD)


def test_parses_observed_outcome_and_delivery_buckets() -> None:
    parsed = parse_iventas_campaign_stats(_payload())
    assert parsed.raw_counts.successful == 3
    assert parsed.raw_counts.failed == 1
    assert parsed.raw_counts.sent == 1
    assert parsed.raw_counts.delivered == 1
    assert parsed.raw_counts.viewed == 1

    assert parsed.successful_phones == frozenset({
        "mx10:6861111111",
        "mx10:6862222222",
        "mx10:6863333333",
    })
    assert parsed.failed_phones == frozenset({
        "mx10:6864444444",
    })
    assert parsed.sent_phones == frozenset({
        "mx10:6861111111",
    })
    assert parsed.delivered_phones == frozenset({
        "mx10:6862222222",
    })
    assert parsed.viewed_phones == frozenset({
        "mx10:6863333333",
    })


def test_not_synced_keeps_valid_buckets_without_analytics() -> None:
    payload = _payload()
    payload["analyticsStatus"] = "not_synced"
    payload.pop("analytics")

    parsed = parse_iventas_campaign_stats(payload)

    assert parsed.analytics_status == "not_synced"
    assert parsed.analytics is None
    assert len(parsed.successful_phones) == 3
    assert len(parsed.failed_phones) == 1


def test_not_synced_accepts_partial_analytics_object() -> None:
    payload = _payload()
    payload["analyticsStatus"] = "not_synced"
    payload["analytics"] = {
        "partial": True,
    }

    parsed = parse_iventas_campaign_stats(payload)

    assert parsed.analytics_status == "not_synced"
    assert parsed.analytics == {
        "partial": True,
    }


def test_raw_counts_are_separate_from_normalized_unique_phones() -> None:
    payload = _payload()
    payload["successfulMessages"] = [
        "6861111111",
        "+52 686 111 1111",
        "6862222222",
        "6863333333",
    ]
    payload["sentMessages"] = [
        "6861111111",
        "+52 686 111 1111",
    ]
    payload["sentdMessages"] = list(
        payload["sentMessages"]
    )

    parsed = parse_iventas_campaign_stats(payload)

    assert parsed.raw_counts.successful == 4
    assert parsed.raw_counts.sent == 2
    assert len(parsed.successful_phones) == 3
    assert len(parsed.sent_phones) == 1


def test_normalized_collision_between_delivery_buckets_is_rejected() -> None:
    payload = _payload()
    payload["deliveredMessages"] = [
        "+52 686 111 1111",
    ]
    with pytest.raises(
        IVentasCampaignStatsInvariantError,
        match="sent/delivered",
    ):
        parse_iventas_campaign_stats(payload)


def test_normalized_collision_between_successful_and_failed_is_rejected() -> None:
    payload = _payload()
    payload["failedMessages"] = [
        "+52 686 111 1111",
    ]

    with pytest.raises(
        IVentasCampaignStatsInvariantError,
        match="successful/failed",
    ):
        parse_iventas_campaign_stats(payload)


def test_sentd_equal_to_sent_is_accepted_without_double_count() -> None:
    parsed = parse_iventas_campaign_stats(_payload())

    assert parsed.raw_counts.sent == 1
    assert parsed.raw_counts.sentd == 1
    assert parsed.sent_phones == frozenset({
        "mx10:6861111111",
    })
def test_sentd_is_legacy_fallback_when_sent_is_absent() -> None:
    payload = _payload()
    payload.pop("sentMessages")

    parsed = parse_iventas_campaign_stats(payload)

    assert parsed.raw_counts.sent == 1
    assert parsed.raw_counts.sentd == 1
    assert parsed.sent_phones == frozenset({
        "mx10:6861111111",
    })


def test_sent_and_sentd_difference_is_rejected() -> None:
    payload = _payload()
    payload["sentdMessages"] = [
        "6869999999",
    ]

    with pytest.raises(
        IVentasCampaignStatsPayloadError,
        match="sentMessages and legacy sentdMessages differ",
    ):
        parse_iventas_campaign_stats(payload)


def test_interactions_keep_raw_count_and_unique_recipients() -> None:
    parsed = parse_iventas_campaign_stats(_payload())

    interaction = parsed.interactions[0]

    assert interaction.label == "Me interesa"
    assert interaction.raw_item_count == 2
    assert interaction.normalized_unique_phones == frozenset({
        "mx10:6863333333",
    })
    assert parsed.raw_counts.interaction_items == 2


def test_answered_messages_do_not_create_individual_responders() -> None:
    parsed = parse_iventas_campaign_stats(_payload())

    assert parsed.raw_counts.answered == 0
    assert parsed.analytics is not None
    assert parsed.analytics["responders"] == 79
    assert parsed.analytics["interactions"] == {
        "campaignButton": 63,
        "freeText": 16,
    }
    assert not hasattr(
        parsed,
        "responded_phones",
    )


def test_extra_provider_fields_are_ignored() -> None:
    payload = _payload()
    payload["providerNewField"] = {
        "future": True,
    }

    parsed = parse_iventas_campaign_stats(payload)

    assert parsed.analytics_status == "ok"
    assert len(parsed.successful_phones) == 3


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "successfulMessages",
            "not-a-list",
            "successfulMessages must be a list",
        ),
        (
            "failedMessages",
            [123],
            "failedMessages must contain only strings",
        ),
        (
            "interactions",
            {},
            "interactions must be a list",
        ),
    ],
)
def test_invalid_provider_shapes_are_rejected(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _payload()
    payload[field] = value

    with pytest.raises(
        IVentasCampaignStatsPayloadError,
        match=message,
    ):
        parse_iventas_campaign_stats(payload)


def test_successful_must_equal_normalized_delivery_union() -> None:
    payload = _payload()
    payload["successfulMessages"] = [
        "6861111111",
        "6862222222",
    ]

    with pytest.raises(
        IVentasCampaignStatsInvariantError,
        match="union",
    ):
        parse_iventas_campaign_stats(payload)


def test_missing_both_sent_keys_is_rejected() -> None:
    payload = _payload()
    payload.pop("sentMessages")
    payload.pop("sentdMessages")

    with pytest.raises(
        IVentasCampaignStatsPayloadError,
        match="sentMessages is required",
    ):
        parse_iventas_campaign_stats(payload)


def test_invalid_analytics_type_is_rejected() -> None:
    payload = _payload()
    payload["analytics"] = []

    with pytest.raises(
        IVentasCampaignStatsPayloadError,
        match="analytics must be an object or null",
    ):
        parse_iventas_campaign_stats(payload)
