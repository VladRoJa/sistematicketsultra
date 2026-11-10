"""Focused operator-evidence tests: no external API, recipients or send."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM as Binding,
    MarketingCampaignV2TemplateORM as Template,
    MarketingCampaignV2TemplateChannelEvidenceORM as Evidence,
)
from app.services.marketing_campaign_v2_bulk_template_evidence_service import (
    BulkInventoryValidation, preview_bulk_template_inventory,
    register_bulk_template_inventory, accepted_bulk_evidence_channels,
    sender_signature,
)
from app.services.marketing_campaign_v2_template_probe_service import _signature

NOW = datetime(2026, 11, 9, 23, 0, tzinfo=timezone.utc)


def template():
    return NS(id=12, template_name="promos_noviembre_v", provider="IVENTAS",
              is_active=True, variables_json={}, metadata_json={},
              compatible_channel_ids_json=["a", "b"])


def binding(ident, channel):
    return NS(id=ident, sucursal_id=ident, sucursal_canon="B" + str(ident),
              provider="IVENTAS", provider_channel_id=channel, is_active=True,
              is_default=True)


def entry(channel, status="accepted"):
    return {"name": "promos_noviembre_v", "status": status, "channelId": channel,
            "channel": {"id": channel, "name": "Suite " + channel}}


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def filter_by(self, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


def make_session(rows=None, evidence=None):
    rows = rows or [binding(1, "a"), binding(2, "b"), binding(3, "c")]
    candidate = template()
    active = MagicMock()
    def query(cls):
        if cls is Template:
            return Query([candidate])
        if cls is Binding:
            return Query(rows)
        if cls is Evidence:
            return Query(evidence or [])
        raise AssertionError("Unexpected table queried")
    active.query.side_effect = query
    active.get.side_effect = lambda cls, ident: next(
        (r for r in rows if cls is Binding and r.id == ident), None
    )
    active.get_bind.return_value.dialect.name = "postgresql"
    return active, candidate, rows


def test_one_inventory_previews_all_senders_without_writes():
    session, _, _ = make_session()
    p = preview_bulk_template_inventory(
        template_id=12, inventory=[entry("a"), entry("b")], session=session,
    )
    assert p["counts"] == {"accepted": 2, "pending": 0, "incompatible": 1}
    assert {r["channel_id"]: r["status"] for r in p["rows"]} == {
        "a": "accepted", "b": "accepted", "c": "incompatible",
    }
    assert p["send_authorized"] is False
    assert p["provider_requests"] == 0
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_register_only_accepted_and_preserve_missing_channels():
    session, _, _ = make_session()
    items = [entry("a"), entry("b", "pending")]
    p = preview_bulk_template_inventory(template_id=12, inventory=items, session=session)
    result = register_bulk_template_inventory(
        template_id=12, inventory=items, session=session,
        observed_at=(NOW - timedelta(minutes=5)).isoformat(),
        source_reference="Inventario iVentas 2026-11-09 verificado",
        expected_fingerprint=p["candidate_fingerprint"],
        confirmed_provider_capture=True, actor_user_id=47, now=NOW,
    )
    assert result["recorded"] == 1
    assert result["pending"] == 2  # one pending and one incompatible
    assert result["send_authorized"] is False
    session.add.assert_called_once()
    assert session.add.call_args.args[0].provider_channel_id == "a"
    session.commit.assert_called_once()


@pytest.mark.parametrize("override", [
    {"confirmed_provider_capture": False},
    {"expected_fingerprint": "0" * 64},
    {"observed_at": (NOW - timedelta(hours=2)).isoformat()},
    {"actor_user_id": 0},
])
def test_no_registration_with_missing_confirmation_stale_data_or_drift(override):
    session, _, _ = make_session()
    items = [entry("a")]
    p = preview_bulk_template_inventory(template_id=12, inventory=items, session=session)
    payload = dict(
        template_id=12, inventory=items, session=session,
        observed_at=(NOW - timedelta(minutes=5)).isoformat(),
        source_reference="Inventario iVentas 2026-11-09 verificado",
        expected_fingerprint=p["candidate_fingerprint"],
        confirmed_provider_capture=True, actor_user_id=47, now=NOW,
    )
    payload.update(override)
    with pytest.raises(BulkInventoryValidation):
        register_bulk_template_inventory(**payload)
    session.commit.assert_not_called()


def test_duplicate_conflicting_provider_inventory_is_not_evidence():
    session, _, _ = make_session()
    with pytest.raises(BulkInventoryValidation):
        preview_bulk_template_inventory(template_id=12,
            inventory=[entry("a"), entry("a", "rejected")], session=session)


def test_reusable_evidence_requires_correct_template_sender_and_fresh_timestamp():
    session, selected, rows = make_session(rows=[binding(1, "a"), binding(2, "b")])
    evidence = [
        NS(id=i, template_id=12, provider_channel_id=row.provider_channel_id,
           sender_binding_id=i, template_signature=_signature(selected),
           sender_signature=sender_signature(row),
           observed_at=NOW - timedelta(minutes=5),
           expires_at=NOW + timedelta(hours=23))
        for i, row in enumerate(rows, 1)
    ]
    session.query.side_effect = lambda cls: (
        Query(evidence) if cls is Evidence else Query([])
    )
    expected = [
        {"channel_binding_id": row.id, "provider_channel_id": row.provider_channel_id}
        for row in rows
    ]
    assert accepted_bulk_evidence_channels(
        template=selected, session=session, outbound_bindings=expected, now=NOW,
    ) == frozenset({"a", "b"})
    evidence[1].expires_at = NOW - timedelta(seconds=1)
    assert accepted_bulk_evidence_channels(
        template=selected, session=session, outbound_bindings=expected, now=NOW,
    ) == frozenset({"a"})
    evidence[1].expires_at = NOW + timedelta(hours=23)
    selected.variables_json = {"1": "first_name"}
    assert not accepted_bulk_evidence_channels(
        template=selected, session=session, outbound_bindings=expected, now=NOW,
    )
    selected.variables_json = {}
    rows[1].provider_channel_id = "other"
    assert accepted_bulk_evidence_channels(
        template=selected, session=session, outbound_bindings=expected, now=NOW,
    ) == frozenset({"a"})
