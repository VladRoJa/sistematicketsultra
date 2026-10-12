"""Offline, read-only validation of iVentas WhatsApp template inventory.

No HTTP requests, credentials, database writes or changes to dispatch config.
The source is an operator-supplied JSON array until an authenticated read API
contract is verified independently.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TemplateAvailability:
    template_name: str
    channel_id: str
    channel_name: str
    status: str


class TemplateInventoryValidationError(ValueError):
    pass


def parse_template_inventory(payload: Any) -> tuple[TemplateAvailability, ...]:
    """Parse the observed iVentas payload, fail closed on ambiguous records."""
    if not isinstance(payload, list):
        raise TemplateInventoryValidationError("Expected a JSON array of templates.")

    seen: dict[tuple[str, str], TemplateAvailability] = {}
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            raise TemplateInventoryValidationError(f"Record {index} must be an object.")
        channel = raw.get("channel")
        if not isinstance(channel, Mapping):
            raise TemplateInventoryValidationError(f"Record {index} has no channel object.")
        name = _text(raw.get("name"))
        channel_id = _text(raw.get("channelId"))
        nested_channel_id = _text(channel.get("id"))
        channel_name = _text(channel.get("name"))
        status = _text(raw.get("status")).lower()
        if not name or not channel_id or not nested_channel_id or not channel_name or not status:
            raise TemplateInventoryValidationError(f"Record {index} has missing fields.")
        if channel_id != nested_channel_id:
            raise TemplateInventoryValidationError(f"Record {index} channel IDs disagree.")
        key = (name.casefold(), channel_id)
        record = TemplateAvailability(name, channel_id, channel_name, status)
        if key in seen and seen[key] != record:
            raise TemplateInventoryValidationError(f"Conflicting template record: {key!r}")
        seen[key] = record
    return tuple(sorted(seen.values(), key=lambda x: (x.template_name, x.channel_id)))


def evaluate_template_coverage(
    *,
    inventory: Sequence[TemplateAvailability],
    expected_channel_ids: Sequence[str],
    template_names: Sequence[str],
) -> dict[str, dict[str, str]]:
    """For each desired template and channel, return accepted, missing or status.

    Only explicit 'accepted' is available. Unknown channels remain missing.
    The provided inventory must be complete for the requested scope; if not,
    'missing' means *not seen in this inventory*, not *absent in iVentas*.
    """
    if not expected_channel_ids or not template_names:
        raise TemplateInventoryValidationError("Channel and template lists must be nonempty.")
    result = {}
    by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in inventory:
        by_pair[(record.template_name.casefold(), record.channel_id)].add(record.status)
    for template in template_names:
        canonical = _text(template)
        if not canonical:
            raise TemplateInventoryValidationError("Empty template name.")
        matrix = {}
        for channel in expected_channel_ids:
            channel_id = _text(channel)
            if not channel_id:
                raise TemplateInventoryValidationError("Empty channel ID.")
            statuses = by_pair.get((canonical.casefold(), channel_id), set())
            matrix[channel_id] = (
                "accepted" if statuses == {"accepted"}
                else "not_observed" if not statuses
                else "conflict" if len(statuses) > 1
                else next(iter(statuses))
            )
        result[canonical] = matrix
    return result


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
