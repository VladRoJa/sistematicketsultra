"""Focused, provider-free tests of manually attested template evidence."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.marketing import (
    MarketingCampaignV2ORM, MarketingCampaignV2TemplateORM,
)
from app.services.marketing_campaign_v2_template_evidence_service import (
    TemplateEvidenceValidation, _capture_time, accepted_evidence_channels,
    register_template_evidence, template_signature,
)


NOW = datetime(2026, 11, 5, 17, 0, tzinfo=timezone.utc)
CHANNELS = ("channel-a", "channel-b", "channel-c")


def row(channel, status="accepted", name="promos_noviembre_v"):
    return {
        "id": "instance", "name": name, "status": status,
        "channelId": channel, "channel": {"id": channel, "name": "Ultra"},
    }


def make_template():
    return SimpleNamespace(
        id=3, template_name="promos_noviembre_v", provider="IVENTAS",
        is_active=True, variables_json={"1": "first_name"},
        compatible_channel_ids_json=list(CHANNELS),
    )


def session_for_registration():
    session = MagicMock()
    campaign = SimpleNamespace(source="PROVIDER_FAILED_DERIVED")
    template = make_template()

    def get(cls, ident):
        if cls is MarketingCampaignV2ORM:
            return campaign
        if cls is MarketingCampaignV2TemplateORM:
            return template
        return None

    session.get.side_effect = get

    def save(row):
        row.id = 123

    session.add.side_effect = save
    return session


def call_registration(session, inventory=None, **override):
    payload = dict(
        campaign_id=42, template_id=3,
        inventory=inventory if inventory is not None else [row(c) for c in CHANNELS],
        observed_at=(NOW - timedelta(minutes=5)).isoformat(),
        source_reference="iVentas inventario observado en panel - ticket 20261105",
        confirmed_provider_capture=True,
        actor_user_id=47, session=session, now=NOW,
    )
    payload.update(override)
    plan = SimpleNamespace(batches=[
        SimpleNamespace(provider_channel_id=c) for c in CHANNELS
    ])
    with patch(
        "app.services.marketing_campaign_v2_preflight_service.build_campaign_v2_preflight",
        return_value=plan,
    ):
        return register_template_evidence(**payload)


def test_exact_all_channel_coverage_records_immutable_proof_without_provider_calls():
    session = session_for_registration()
    result = call_registration(session)
    assert result["accepted_channel_ids"] == list(CHANNELS)
    assert result["send_authorized"] is False
    assert result["provider_api_verified"] is False
    assert result["quota_reserved"] is False
    assert len(result["inventory_sha256"]) == 64
    assert session.add.call_count == 1
    session.commit.assert_called_once()
    stored = session.add.call_args.args[0]
    assert stored.campaign_id == 42
    assert stored.template_signature == template_signature(make_template())


@pytest.mark.parametrize("inventory", [
    [row("channel-a"), row("channel-b")],
    [row("channel-a"), row("channel-b"), row("channel-c", status="denied")],
    [row("channel-a"), row("channel-b"), row("channel-c", name="other")],
    [row("channel-a"), row("channel-b"), row("channel-c") | {"channelId": "wrong"}],
])
def test_missing_denied_wrong_or_ambiguous_inventory_never_unblocks(inventory):
    session = session_for_registration()
    with pytest.raises(TemplateEvidenceValidation):
        call_registration(session, inventory)
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_old_future_or_timezone_free_capture_is_rejected():
    for stamp in [
        (NOW - timedelta(hours=2)).isoformat(),
        (NOW + timedelta(minutes=5)).isoformat(),
        "2026-11-05T16:00:00",
    ]:
        with pytest.raises(TemplateEvidenceValidation):
            _capture_time(stamp, NOW)


def test_no_operator_confirmation_no_evidence_persisted():
    session = session_for_registration()
    with pytest.raises(TemplateEvidenceValidation, match="confirmarse"):
        call_registration(session, confirmed_provider_capture=False)
    session.commit.assert_not_called()


def test_evidence_revoked_by_expiry_or_template_drift():
    original = make_template()
    old = SimpleNamespace(
        id=8, template_name=original.template_name,
        template_signature=template_signature(original),
        observed_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=23),
        accepted_channel_ids_json=list(CHANNELS),
    )
    session = MagicMock()
    session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = old
    assert accepted_evidence_channels(
        campaign_id=42, template=original, session=session, now=NOW
    ) == frozenset(CHANNELS)
    old.expires_at = NOW - timedelta(seconds=1)
    assert not accepted_evidence_channels(
        campaign_id=42, template=original, session=session, now=NOW
    )
    old.expires_at = NOW + timedelta(hours=23)
    changed = make_template()
    changed.variables_json = {"1": "member_id"}
    assert not accepted_evidence_channels(
        campaign_id=42, template=changed, session=session, now=NOW
    )
