"""Parser puro de estadísticas de campañas iVentas.

M8: no HTTP, no persistencia, no ORM.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from app.services.marketing_iventas_service import normalize_iventas_phone


class IVentasCampaignStatsPayloadError(ValueError):
    """Payload iVentas inválido o incompatible con el contrato observado."""


class IVentasCampaignStatsInvariantError(
    IVentasCampaignStatsPayloadError
):
    """Buckets incompatibles después de normalización telefónica."""


@dataclass(frozen=True)
class IVentasCampaignStatsRawCounts:
    successful: int
    failed: int
    sent: int
    delivered: int
    viewed: int
    answered: int
    sentd: int | None
    interaction_groups: int
    interaction_items: int


@dataclass(frozen=True)
class IVentasCampaignInteraction:
    label: str
    raw_item_count: int
    normalized_unique_phones: frozenset[str]


@dataclass(frozen=True)
class IVentasCampaignStats:
    analytics_status: str | None
    analytics: Mapping[str, Any] | None
    raw_counts: IVentasCampaignStatsRawCounts
    successful_phones: frozenset[str]
    failed_phones: frozenset[str]
    sent_phones: frozenset[str]
    delivered_phones: frozenset[str]
    viewed_phones: frozenset[str]
    interactions: tuple[IVentasCampaignInteraction, ...]


def _require_string_list(
    payload: Mapping[str, Any],
    key: str,
    *,
    required: bool = True,
) -> list[str] | None:
    if key not in payload:
        if required:
            raise IVentasCampaignStatsPayloadError(
                f"{key} is required"
            )
        return None

    value = payload[key]

    if not isinstance(value, list):
        raise IVentasCampaignStatsPayloadError(
            f"{key} must be a list"
        )
    if not all(
        isinstance(item, str)
        for item in value
    ):
        raise IVentasCampaignStatsPayloadError(
            f"{key} must contain only strings"
        )

    return value


def _normalized_phone_key(value: str) -> str:
    normalized = normalize_iventas_phone(value)

    if normalized.phone_mx10:
        return f"mx10:{normalized.phone_mx10}"

    if normalized.phone_digits:
        return f"digits:{normalized.phone_digits}"

    raw = (normalized.phone_raw or "").strip()

    if raw:
        return f"raw:{raw}"

    raise IVentasCampaignStatsPayloadError(
        "recipient phone cannot be empty"
    )
def _normalize_phone_set(
    values: list[str],
) -> frozenset[str]:
    return frozenset(
        _normalized_phone_key(value)
        for value in values
    )


def _parse_interactions(
    payload: Mapping[str, Any],
) -> tuple[
    tuple[IVentasCampaignInteraction, ...],
    int,
]:
    raw = payload.get("interactions", [])

    if not isinstance(raw, list):
        raise IVentasCampaignStatsPayloadError(
            "interactions must be a list"
        )

    parsed: list[IVentasCampaignInteraction] = []
    total_items = 0

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise IVentasCampaignStatsPayloadError(
                f"interactions[{index}] must be an object"
            )
        label = item.get("label")
        items = item.get("items")

        if not isinstance(label, str):
            raise IVentasCampaignStatsPayloadError(
                f"interactions[{index}].label must be a string"
            )

        if not isinstance(items, list):
            raise IVentasCampaignStatsPayloadError(
                f"interactions[{index}].items must be a list"
            )

        if not all(
            isinstance(phone, str)
            for phone in items
        ):
            raise IVentasCampaignStatsPayloadError(
                f"interactions[{index}].items must contain only strings"
            )

        total_items += len(items)
        parsed.append(
            IVentasCampaignInteraction(
                label=label,
                raw_item_count=len(items),
                normalized_unique_phones=_normalize_phone_set(
                    items
                ),
            )
        )

    return tuple(parsed), total_items


def _validate_invariants(
    *,
    successful: frozenset[str],
    failed: frozenset[str],
    sent: frozenset[str],
    delivered: frozenset[str],
    viewed: frozenset[str],
) -> None:
    incompatible_pairs = (
        ("sent", sent, "delivered", delivered),
        ("sent", sent, "viewed", viewed),
        ("delivered", delivered, "viewed", viewed),
        ("successful", successful, "failed", failed),
    )

    for left_name, left, right_name, right in incompatible_pairs:
        if left & right:
            raise IVentasCampaignStatsInvariantError(
                "normalized phone appears in incompatible buckets: "
                f"{left_name}/{right_name}"
            )
    delivery_union = sent | delivered | viewed

    if successful != delivery_union:
        raise IVentasCampaignStatsInvariantError(
            "successful bucket does not equal normalized "
            "union(sent, delivered, viewed)"
        )


def parse_iventas_campaign_stats(
    payload: Mapping[str, Any],
) -> IVentasCampaignStats:
    """Normaliza un payload real observado de campaign stats."""

    if not isinstance(payload, Mapping):
        raise IVentasCampaignStatsPayloadError(
            "payload must be an object"
        )

    successful_raw = _require_string_list(
        payload,
        "successfulMessages",
    )
    failed_raw = _require_string_list(
        payload,
        "failedMessages",
    )
    sent_raw = _require_string_list(
        payload,
        "sentMessages",
        required=False,
    )
    sentd_raw = _require_string_list(
        payload,
        "sentdMessages",
        required=False,
    )

    if sent_raw is None and sentd_raw is None:
        raise IVentasCampaignStatsPayloadError(
            "sentMessages is required unless legacy sentdMessages exists"
        )

    if (
        sent_raw is not None
        and sentd_raw is not None
        and set(sent_raw) != set(sentd_raw)
    ):
        raise IVentasCampaignStatsPayloadError(
            "sentMessages and legacy sentdMessages differ"
        )

    canonical_sent_raw = (
        sent_raw
        if sent_raw is not None
        else sentd_raw
    )

    delivered_raw = _require_string_list(
        payload,
        "deliveredMessages",
    )
    viewed_raw = _require_string_list(
        payload,
        "viewedMessages",
    )
    answered_raw = _require_string_list(
        payload,
        "answeredMessages",
        required=False,
    ) or []

    successful = _normalize_phone_set(successful_raw)
    failed = _normalize_phone_set(failed_raw)
    sent = _normalize_phone_set(canonical_sent_raw or [])
    delivered = _normalize_phone_set(delivered_raw)
    viewed = _normalize_phone_set(viewed_raw)

    _validate_invariants(
        successful=successful,
        failed=failed,
        sent=sent,
        delivered=delivered,
        viewed=viewed,
    )

    interactions, interaction_items = _parse_interactions(
        payload
    )

    analytics_status_raw = payload.get("analyticsStatus")
    if (
        analytics_status_raw is not None
        and not isinstance(analytics_status_raw, str)
    ):
        raise IVentasCampaignStatsPayloadError(
            "analyticsStatus must be a string or null"
        )

    analytics_raw = payload.get("analytics")
    if (
        analytics_raw is not None
        and not isinstance(analytics_raw, Mapping)
    ):
        raise IVentasCampaignStatsPayloadError(
            "analytics must be an object or null"
        )

    analytics = (
        deepcopy(dict(analytics_raw))
        if analytics_raw is not None
        else None
    )

    raw_counts = IVentasCampaignStatsRawCounts(
        successful=len(successful_raw),
        failed=len(failed_raw),
        sent=len(canonical_sent_raw or []),
        delivered=len(delivered_raw),
        viewed=len(viewed_raw),
        answered=len(answered_raw),
        sentd=(
            len(sentd_raw)
            if sentd_raw is not None
            else None
        ),
        interaction_groups=len(interactions),
        interaction_items=interaction_items,
    )

    return IVentasCampaignStats(
        analytics_status=analytics_status_raw,
        analytics=analytics,
        raw_counts=raw_counts,
        successful_phones=successful,
        failed_phones=failed,
        sent_phones=sent,
        delivered_phones=delivered,
        viewed_phones=viewed,
        interactions=interactions,
    )
