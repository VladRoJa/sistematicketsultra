"""Issue 856 D1 — capacity assessment is conservative and read-only."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.services import marketing_campaign_v2_quota_service as quota
from app.models.marketing import (
    MarketingCampaignV2QuotaPolicyRevisionORM as Policy,
    MarketingCampaignV2QuotaCapacityAttestationORM as Evidence,
    MarketingCampaignV2ProviderCampaignORM as Child,
)

NOW = datetime(2026, 10, 13, 17, 0, tzinfo=timezone.utc)


def policy(channel, portfolio, *, id=1):
    return NS(
        id=id, provider_channel_id=channel, portfolio_key=portfolio,
        account_key="wa-account", phone_alias="wa-num", nominal_channel_limit=250,
        reset_timezone="America/Tijuana", valid_from=NOW-timedelta(hours=2),
        source_reference="synthetic-channel-contract",
    )


def evidence(kind, key, remaining, *, id=1, expires=True):
    return NS(
        id=id, scope_kind=kind, scope_key=key, remaining_messages=remaining,
        observed_at=NOW-timedelta(minutes=10),
        expires_at=NOW+timedelta(minutes=10) if expires else NOW-timedelta(seconds=1),
        window_ends_at=NOW+timedelta(hours=10),
        source_reference="operator-reported-synthetic-evidence",
    )


def batch(branch, channel, count):
    return NS(
        sucursal_canon=branch, provider_channel_id=channel,
        recipients=[NS(phone_mx10=str(i)) for i in range(count)],
    )


def fake_session(policies=None, capacity=None, events=None):
    session = MagicMock()
    policies = policies if policies is not None else []
    capacity = capacity if capacity is not None else []
    events = events if events is not None else []
    def get_query(model):
        q = MagicMock()
        if model is Policy:
            q.filter.return_value.order_by.return_value.all.return_value = policies
            q.filter.return_value.all.return_value = policies
        elif model is Evidence:
            q.filter.return_value.order_by.return_value.all.return_value = capacity
        elif model is Child:
            q.filter.return_value.all.return_value = events
        return q
    session.query.side_effect = get_query
    return session


def assess(batches, *, policies=None, capacity=None, events=None):
    session = fake_session(policies, capacity, events)
    result = quota.assess_preflight_capacity(
        plan=NS(batches=batches), session=session, now=NOW,
    )
    session.add.assert_not_called()
    session.commit.assert_not_called()
    return result


def test_no_quota_evidence_is_not_silently_available():
    result = assess([batch("A", "one", 3)])
    assert result["status"] == "INCOMPLETE"
    assert result["send_authorized"] is False
    assert result["hold_recommended_recipients"] == 3
    assert result["batches"][0]["blocking_reason"] == "MISSING_QUOTA_POLICY"


def test_shared_portfolio_capacity_aggregates_across_branches():
    policies = [policy("one", "shared"), policy("two", "shared", id=2)]
    capacity = [
        evidence("CHANNEL", "one", 100),
        evidence("CHANNEL", "two", 100, id=2),
        evidence("PORTFOLIO", "shared", 50, id=3),
    ]
    result = assess(
        [batch("A","one",40), batch("B","two",40)],
        policies=policies, capacity=capacity,
    )
    assert result["status"] == "INCOMPLETE"
    assert result["hold_recommended_recipients"] == 80
    assert result["portfolio_demands"] == [{
        "portfolio_key": "shared", "recipients": 80, "attested_remaining": 50,
    }]
    assert all(item["blocking_reason"] == "SHARED_PORTFOLIO_REMAINING_EXCEEDED"
               for item in result["batches"])


def test_held_children_are_not_counted_as_consumption():
    policies = [policy("one", "shared")]
    capacity = [
        evidence("CHANNEL", "one", 100),
        evidence("PORTFOLIO", "shared", 100, id=2),
    ]
    held = NS(provider_channel_id="one", status="HELD",
              submit_started_at=None, submitted_at=None,
              created_at=NOW-timedelta(minutes=1))
    result = assess([batch("A","one",80)], policies=policies,
                    capacity=capacity, events=[held])
    assert result["status"] == "REVIEWABLE"
    assert result["reviewed_recipients"] == 80
    assert result["send_authorized"] is False


def test_event_from_other_channel_same_portfolio_invalidates_older_evidence():
    policies = [policy("one","shared"), policy("two","shared",id=2)]
    capacity = [
        evidence("CHANNEL","one",500),
        evidence("PORTFOLIO","shared",500,id=2),
    ]
    attempt = NS(provider_channel_id="two",status="SUBMITTED",
                 submit_started_at=NOW-timedelta(minutes=3),
                 submitted_at=NOW-timedelta(minutes=2),created_at=NOW-timedelta(hours=1))
    result = assess([batch("A","one",100)], policies=policies,
                    capacity=capacity,events=[attempt])
    assert result["batches"][0]["blocking_reason"] == "ACTIVITY_AFTER_QUOTA_ATTESTATION"
    assert result["send_authorized"] is False


def test_channel_or_portfolio_shortage_always_requires_hold_review():
    p=[policy("one","shared")]
    for caps, expected in [
        ([evidence("CHANNEL","one",5), evidence("PORTFOLIO","shared",100,id=2)],
         "CHANNEL_REMAINING_EXCEEDED"),
        ([evidence("CHANNEL","one",100)],"MISSING_VERIFIED_REMAINING"),
    ]:
        result=assess([batch("A","one",10)],policies=p,capacity=caps)
        assert result["batches"][0]["blocking_reason"] == expected


@pytest.mark.parametrize("remaining", [-1, True, "100", None])
def test_remaining_must_be_an_explicit_integer(remaining):
    with pytest.raises(quota.CampaignV2QuotaValidationError):
        quota.register_quota_capacity(
            scope_kind="PORTFOLIO", scope_key="shared",
            observed_at=NOW.isoformat(),
            expires_at=(NOW+timedelta(minutes=5)).isoformat(),
            window_ends_at=(NOW+timedelta(hours=3)).isoformat(),
            remaining_messages=remaining, source_reference="manual proof",
            actor_user_id=7, session=fake_session(),
            now=NOW,
        )


def test_capacity_expiry_and_observation_order_are_strict():
    with pytest.raises(quota.CampaignV2QuotaValidationError, match="Vigencia"):
        quota.register_quota_capacity(
            scope_kind="CHANNEL", scope_key="one",
            observed_at=(NOW+timedelta(hours=1)).isoformat(),
            expires_at=(NOW+timedelta(hours=2)).isoformat(),
            window_ends_at=(NOW+timedelta(hours=3)).isoformat(),
            remaining_messages=10, source_reference="manual proof",
            actor_user_id=7, session=fake_session(),now=NOW,
        )


def test_policy_rejects_unrecognized_timezone_before_any_write():
    session=fake_session()
    with pytest.raises(quota.CampaignV2QuotaValidationError, match="Zona horaria"):
        quota.register_quota_policy(
            provider_channel_id="one", portfolio_key="shared",
            account_key="acc", phone_alias="phone",
            nominal_channel_limit=None, reset_timezone="NO_SUCH_ZONE",
            source_reference="contract", actor_user_id=7,
            session=session, now=NOW,
        )
    session.add.assert_not_called()
    session.commit.assert_not_called()
