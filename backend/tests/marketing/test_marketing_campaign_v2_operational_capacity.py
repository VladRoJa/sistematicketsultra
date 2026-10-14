"""Issue 856 internal rolling caps: no fabricated Meta remainder; no sends."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.services import marketing_campaign_v2_operational_capacity_service as svc
from app.services import marketing_campaign_v2_quota_service as quotas
from app.models.marketing import (
    MarketingCampaignV2QuotaPolicyRevisionORM as Policy,
    MarketingCampaignV2CapacityReservationORM as Reservation,
    MarketingCampaignV2ProviderCampaignORM as Child,
)

NOW = datetime(2026, 10, 14, 17, 0, tzinfo=timezone.utc)


def policy(channel, portfolio="shared", channel_cap=100, portfolio_cap=200, id=1):
    return NS(
        id=id, provider_channel_id=channel, portfolio_key=portfolio,
        account_key="wa1", phone_alias="wa1", reset_timezone="America/Tijuana",
        nominal_channel_limit=100000,
        operational_channel_cap=channel_cap,
        operational_portfolio_cap=portfolio_cap,
        source_reference="policy document test", valid_from=NOW - timedelta(days=2),
    )


def batch(branch, channel, count):
    return NS(
        sucursal_canon=branch, provider_channel_id=channel,
        recipients=[NS(phone_mx10="6860000000") for _ in range(count)],
    )


def event(channel, count, *, mins=5, status="SUBMITTED", resolution=None):
    return NS(
        campaign_v2_id=501, provider="IVENTAS", provider_channel_id=channel,
        recipient_count=count, status=status, reconciliation_resolution=resolution,
        submit_started_at=NOW-timedelta(minutes=mins),
        submitted_at=NOW-timedelta(minutes=mins),
        created_at=NOW-timedelta(minutes=mins + 1),
    )


def reservation(kind, key, count):
    return NS(scope_kind=kind, scope_key=key, reserved_messages=count,
              reserved_until=NOW+timedelta(minutes=10), approval_id=40)


def session(policies, events=(), reservations=()):
    fake = MagicMock()

    def query(model):
        result = MagicMock()
        if model is Policy:
            result.filter.return_value.order_by.return_value.all.return_value = list(policies)
        elif model is Child:
            result.filter.return_value.all.return_value = list(events)
        elif model is Reservation:
            result.join.return_value.filter.return_value.all.return_value = list(reservations)
        return result

    fake.query.side_effect = query
    return fake


def assess(batches, policies, events=(), reservations=(), ignored=None):
    s = session(policies, events, reservations)
    result = svc.assess_operational_capacity(
        plan=NS(batches=batches), session=s, now=NOW,
        ignore_campaign_id=ignored,
    )
    s.add.assert_not_called()
    s.commit.assert_not_called()
    return result


def test_no_operational_cap_preserves_legacy_attestation_contract():
    p = policy("ch1")
    p.operational_channel_cap = None
    p.operational_portfolio_cap = None
    assert assess([batch("A", "ch1", 1)], [p]) is None


def test_one_recipient_passes_without_meta_remaining_or_attestations():
    r = assess([batch("AZAHARES", "ch1", 1)], [policy("ch1")])
    assert r["basis"] == svc.BASIS
    assert r["status"] == "REVIEWABLE"
    assert r["actual_meta_remaining"] is None
    assert r["send_authorized"] is False
    assert r["window_start"] == (NOW - timedelta(hours=24)).isoformat()
    assert r["batches"][0]["channel_evidence_id"] is None
    assert r["batches"][0]["policy_revision_id"] == 1
    assert r["batches"][0]["suite_channel_attempted"] == 0


def test_shared_portfolio_demand_aggregates_26_style_batches():
    r = assess([
        batch("A", "ch1", 7), batch("B", "ch2", 6),
    ], [policy("ch1", portfolio_cap=12),
        policy("ch2", portfolio_cap=12, id=2)])
    assert r["status"] == "INCOMPLETE"
    assert all(x["blocking_reason"] == "PORTFOLIO_OPERATOR_LIMIT_EXCEEDED"
               for x in r["batches"])


def test_suite_attempts_and_active_reservations_count_conservatively():
    r = assess(
        [batch("A", "ch1", 2)],
        [policy("ch1", channel_cap=10, portfolio_cap=10)],
        events=[event("ch1", 5)],
        reservations=[reservation("CHANNEL", "ch1", 4)],
    )
    assert r["status"] == "INCOMPLETE"
    assert r["batches"][0]["blocking_reason"] == "CHANNEL_OPERATOR_LIMIT_EXCEEDED"
    assert r["batches"][0]["suite_channel_attempted"] == 5
    assert r["batches"][0]["suite_channel_reserved"] == 4


def test_another_channel_counts_against_same_portfolio():
    r = assess([batch("A", "ch1", 2)],
               [policy("ch1", portfolio_cap=10),
                policy("ch2", portfolio_cap=10, id=2)],
               events=[event("ch2", 9)])
    assert r["batches"][0]["blocking_reason"] == "PORTFOLIO_OPERATOR_LIMIT_EXCEEDED"


def test_deterministic_not_created_is_not_counted():
    r = assess([batch("A", "ch1", 1)],
               [policy("ch1", channel_cap=1, portfolio_cap=1)],
               events=[event("ch1", 100, status="PROVIDER_ERROR",
                             resolution="NOT_CREATED_CONFIRMED")])
    assert r["status"] == "REVIEWABLE"


def test_unreconciled_old_attempt_fails_closed():
    r = assess([batch("A", "ch1", 1)], [policy("ch1")],
               events=[event("ch1", 1, mins=1500, status="RECONCILIATION_REQUIRED")])
    assert r["batches"][0]["blocking_reason"] == "UNRESOLVED_PROVIDER_ACTIVITY"


def test_conflicting_limits_for_shared_portfolio_fail_closed():
    r = assess([batch("A", "ch1", 1)],
               [policy("ch1", portfolio_cap=200),
                policy("ch2", portfolio_cap=100, id=2)])
    assert r["status"] == "INCOMPLETE"
    assert r["batches"][0]["blocking_reason"] == "SHARED_PORTFOLIO_POLICY_CONFLICT"


@pytest.mark.parametrize("caps", [(5, None), (None, 6), (0, 6), (6, -1)])
def test_registration_rejects_partial_or_nonpositive_operator_caps(caps):
    with pytest.raises(quotas.CampaignV2QuotaValidationError):
        quotas.register_quota_policy(
            provider_channel_id="channel", portfolio_key="shared",
            account_key="account", phone_alias="phone", nominal_channel_limit=100,
            operational_channel_cap=caps[0], operational_portfolio_cap=caps[1],
            reset_timezone="America/Tijuana", source_reference="test evidence",
            actor_user_id=7, session=MagicMock(), now=NOW,
        )


def test_new_basis_explicitly_forced_even_when_policy_missing():
    r = svc.assess_operational_capacity(
        plan=NS(batches=[batch("A", "ch1", 1)]),
        session=session([]), now=NOW, force=True,
    )
    assert r["basis"] == svc.BASIS
    assert r["status"] == "INCOMPLETE"
    assert r["batches"][0]["blocking_reason"] == "MISSING_QUOTA_POLICY"
