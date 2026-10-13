"""Issue #856 C — partially accepted origin is not an all-or-nothing campaign."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.services.marketing_campaign_v2_dispatch_exclusion_service import (
    CampaignV2ScopedExclusionValidationError,
    _submitted_phone_set,
)

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)

def child(number: str, state: str, channel: str, **kwargs):
    data = {
        "status": state,
        "provider_campaign_id": "accepted-reference" if state == "SUBMITTED" else None,
        "submitted_at": NOW if state == "SUBMITTED" else None,
        "submit_started_at": None,
        "hold_reason": "CHANNEL_DAILY_QUOTA" if state == "HELD" else None,
        "held_by_user_id": 7 if state == "HELD" else None,
        "held_at": NOW if state == "HELD" else None,
        "hold_evidence_json": {"source": "synthetic"} if state == "HELD" else {},
        "provider_channel_id": channel,
        "recipient_count": 1,
        "request_snapshot_json": {
            "provider_channel_id": channel,
            "leads": [{"phone": number, "variables": []}],
        },
    }
    data.update(kwargs)
    return NS(**data)

def origin(rows):
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = rows
    return _submitted_phone_set(source_campaign_id=15, session=session)

def test_only_accepted_contact_is_suppressed_with_two_held():
    accepted = child("5216861111111", "SUBMITTED", "regular")
    held_a = child("5216862222222", "HELD", "limited-a")
    held_b = child("5216863333333", "HELD", "limited-b")
    assert origin([accepted, held_a, held_b]) == {"6861111111"}

@pytest.mark.parametrize("tamper", [
    {"hold_evidence_json": {}},
    {"held_by_user_id": None},
    {"held_at": None},
    {"provider_campaign_id": "unexpected"},
    {"submit_started_at": NOW},
    {"submitted_at": NOW},
])
def test_tampered_held_never_proves_safe_source(tamper):
    with pytest.raises(CampaignV2ScopedExclusionValidationError):
        origin([
            child("5216861111111", "SUBMITTED", "regular"),
            child("5216862222222", "HELD", "limited", **tamper),
        ])

@pytest.mark.parametrize("state", [
    "READY", "SUBMITTING", "PROVIDER_ERROR",
    "RECONCILIATION_REQUIRED", "SCHEDULED",
])
def test_non_held_partial_source_fails_closed(state):
    with pytest.raises(CampaignV2ScopedExclusionValidationError):
        origin([
            child("5216861111111", "SUBMITTED", "regular"),
            child("5216862222222", state, "unknown"),
        ])

def test_only_held_is_not_accepted_campaign():
    with pytest.raises(CampaignV2ScopedExclusionValidationError):
        origin([child("5216862222222", "HELD", "limited")])
