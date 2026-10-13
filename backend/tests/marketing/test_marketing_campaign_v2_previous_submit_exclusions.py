"""Safety tests for cross-campaign suppression backed by accepted payloads."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.services import marketing_campaign_v2_dispatch_exclusion_service as svc


def child(*phones, status="SUBMITTED", provider_campaign_id="provider-1",
          submitted_at=None, channel_id="channel-1", count=None):
    return NS(
        status=status,
        provider_campaign_id=provider_campaign_id,
        submitted_at=submitted_at or datetime(2026, 10, 12, tzinfo=timezone.utc),
        provider_channel_id=channel_id,
        recipient_count=len(phones) if count is None else count,
        hold_reason="CHANNEL_DAILY_QUOTA",
        held_by_user_id=7,
        held_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        hold_evidence_json={"reason": "synthetic limited channel"},
        submit_started_at=None,
        request_snapshot_json={
            "provider_channel_id": channel_id,
            "leads": [{"phone": phone, "variables": []} for phone in phones],
        },
    )


def session_with_children(children):
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = children
    return session


def test_exact_submitted_payload_not_frozen_recipients():
    rows = [
        child("5216861234567", channel_id="a"),
        child("5216867654321", channel_id="b"),
    ]
    assert svc._submitted_phone_set(
        source_campaign_id=14,
        session=session_with_children(rows),
    ) == {"6861234567", "6867654321"}


@pytest.mark.parametrize("rows", [
    [],
    [child("5216861234567", status="READY")],
    [child("5216861234567", status="RECONCILIATION_REQUIRED")],
    [child("5216861234567", status="PROVIDER_ERROR")],
    [child("5216861234567", provider_campaign_id="")],
    [child("5216861234567", count=2)],
    [child("5216861234567", "5216861234567")],
    [child("526861234567")],
])
def test_missing_partial_or_malformed_prior_evidence_fails_closed(rows):
    with pytest.raises(svc.CampaignV2ScopedExclusionValidationError):
        svc._submitted_phone_set(source_campaign_id=14, session=session_with_children(rows))


def test_prior_provider_snapshot_missing_leads_fails_closed():
    row = child("5216861234567")
    row.request_snapshot_json = {}
    with pytest.raises(svc.CampaignV2ScopedExclusionValidationError):
        svc._submitted_phone_set(
            source_campaign_id=14, session=session_with_children([row]),
        )


def setup_find(monkeypatch, *, target_time=None, source_time=None):
    target = NS(frozen_at=target_time or datetime(2026, 10, 12, 23, tzinfo=timezone.utc))
    source = NS(frozen_at=source_time or datetime(2026, 10, 12, 22, tzinfo=timezone.utc))
    session = MagicMock()
    session.get.side_effect = lambda cls, campaign_id: (
        target if campaign_id == 15 else source
    )
    session.query.return_value.filter.return_value.all.return_value = [
        (100, "6861234567"),
        (101, "6861234568"),
        (102, "6861234569"),
    ]
    monkeypatch.setattr(svc, "get_campaign_v2", lambda **kwargs: {"id": kwargs["campaign_id"]})
    monkeypatch.setattr(
        svc, "_submitted_phone_set",
        lambda **kwargs: {"6861234567", "6861234569"},
    )
    return session


def test_read_only_match_uses_submitted_phone_membership(monkeypatch):
    session = setup_find(monkeypatch)
    proof = svc.find_previous_campaign_contact_ids(
        campaign_id=15, source_campaign_id=14,
        allowed_sucursal_keys=None, session=session,
    )
    assert proof["matched_recipient_ids"] == [100, 102]
    assert proof["matched"] == 2
    assert proof["source_submitted_phones_count"] == 2
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize("source_id,target_id", [(14, 14), (0, 15), (14, 0)])
def test_invalid_campaign_identifiers_fail_before_queries(source_id, target_id):
    session = MagicMock()
    with pytest.raises(svc.CampaignV2ScopedExclusionValidationError):
        svc.find_previous_campaign_contact_ids(
            campaign_id=target_id, source_campaign_id=source_id,
            allowed_sucursal_keys=None, session=session,
        )
    session.query.assert_not_called()


def setup_write(monkeypatch, *, existing=(), has_children=False, matched=2):
    proof = {
        "campaign_id": 15,
        "source_campaign_id": 14,
        "source_submitted_phones_count": 2,
        "matched_recipient_ids": [100, 102],
        "matched": matched,
    }
    monkeypatch.setattr(svc, "find_previous_campaign_contact_ids", lambda **kw: proof)
    session = MagicMock()
    campaign_q = MagicMock()
    campaign_q.filter.return_value.with_for_update.return_value.one.return_value = NS(
        frozen_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
    )
    children_q = MagicMock()
    children_q.filter.return_value.first.return_value = object() if has_children else None
    exclusions_q = MagicMock()
    exclusions_q.filter.return_value.all.return_value = list(existing)
    session.query.side_effect = lambda kind: (
        campaign_q if kind is svc.MarketingCampaignV2ORM
        else children_q if kind is svc.MarketingCampaignV2ProviderCampaignORM.id
        else exclusions_q
    )
    return session


def test_add_is_transaction_owned_and_audited(monkeypatch):
    session = setup_write(monkeypatch)
    result = svc.add_campaign_v2_previous_campaign_contact_exclusions(
        campaign_id=15, source_campaign_id=14,
        actor_user_id=47, expected_count=2,
        allowed_sucursal_keys=None, session=session,
    )
    assert result["added"] == 2
    assert session.add.call_count == 2
    for call in session.add.call_args_list:
        row = call.args[0]
        assert row.campaign_id == 15
        assert row.related_campaign_id == 14
        assert row.reason == svc.PREVIOUS_CAMPAIGN_CONTACT
        assert row.created_by_user_id == 47
    session.flush.assert_called_once()
    session.commit.assert_not_called()


def test_repeat_is_idempotent(monkeypatch):
    existing = (
        NS(recipient_id=100, reason=svc.PREVIOUS_CAMPAIGN_CONTACT, related_campaign_id=14),
        NS(recipient_id=102, reason=svc.PREVIOUS_CAMPAIGN_CONTACT, related_campaign_id=14),
    )
    session = setup_write(monkeypatch, existing=existing)
    result = svc.add_campaign_v2_previous_campaign_contact_exclusions(
        campaign_id=15, source_campaign_id=14,
        actor_user_id=47, expected_count=2,
        allowed_sucursal_keys=None, session=session,
    )
    assert result["added"] == 0
    assert result["already_present"] == 2
    session.add.assert_not_called()


@pytest.mark.parametrize("existing,children,expected", [
    ((), True, 2),
    ((NS(recipient_id=100, reason="AMBIGUOUS_BRANCH_EVIDENCE",
         related_campaign_id=None),), False, 2),
    ((), False, 3),
])
def test_write_fails_closed_on_provider_children_reason_or_count(
    monkeypatch, existing, children, expected
):
    session = setup_write(monkeypatch, existing=existing, has_children=children)
    with pytest.raises(svc.CampaignV2ScopedExclusionValidationError):
        svc.add_campaign_v2_previous_campaign_contact_exclusions(
            campaign_id=15, source_campaign_id=14,
            actor_user_id=47, expected_count=expected,
            allowed_sucursal_keys=None, session=session,
        )
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_model_db_check_requires_provenance_and_distinct_campaign():
    from app.models.marketing import MarketingCampaignV2RecipientDispatchExclusionORM
    constraints = {
        c.name: str(c.sqltext)
        for c in MarketingCampaignV2RecipientDispatchExclusionORM.__table__.constraints
        if hasattr(c, "sqltext")
    }
    reason = constraints["ck_mkt_v2_recipient_dispatch_exclusion_reason"]
    assert "PREVIOUS_CAMPAIGN_CONTACT" in reason
    assert "related_campaign_id IS NOT NULL" in reason
    assert "AMBIGUOUS_BRANCH_EVIDENCE" in reason
    assert "related_campaign_id <> campaign_id" in constraints[
        "ck_mkt_v2_recipient_dispatch_exclusion_source_diff"
    ]
