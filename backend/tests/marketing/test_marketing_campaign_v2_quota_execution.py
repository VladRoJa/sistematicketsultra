"""D2c gate behavior: no implicit send, one durable claim, never replay."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest

from app.services import marketing_campaign_v2_governed_dispatch_service as svc

NOW = datetime(2026, 10, 13, 17, tzinfo=timezone.utc)
DIGEST = "a" * 64


def plan():
    return NS(
        campaign_id=99, provider="IVENTAS",
        batches=(
            NS(sucursal_canon="A", recipients=[NS()] * 5),
            NS(sucursal_canon="B", recipients=[NS()] * 7),
        ),
    )


def manifest():
    return {
        "A": {"planned_status": "READY"},
        "B": {"planned_status": "HELD"},
    }


def children():
    return [NS(id=100, sucursal_canon="A", status="READY",
               submit_started_at=None, submitted_by_user_id=None,
               updated_at=NOW, error_code=None, support_ref=None),
            NS(id=101, sucursal_canon="B", status="HELD")]


def execution(status="AUTHORIZED"):
    return NS(id=41, status=status, approval_id=9,
              manifest_digest=DIGEST, last_child_id=None,
              expires_at=NOW+timedelta(minutes=9), updated_at=NOW)


def review():
    return NS(id=9, expires_at=NOW+timedelta(minutes=9)), plan(), manifest(), children(), DIGEST


def fake_authorized_session(exec_obj):
    session = MagicMock()
    query = session.query.return_value
    query.filter.return_value.with_for_update.return_value.one_or_none.return_value = exec_obj
    session.get.return_value = exec_obj
    return session


def test_dispatch_rejects_each_switch_before_provider_or_database_access():
    provider = MagicMock()
    session = MagicMock()
    for a, b in [(False, True), (True, False), (False, False)]:
        with pytest.raises(svc.GovernedDispatchDisabled):
            svc.execute_governed_child(
                campaign_id=99, execution_id=41, child_id=100,
                expected_digest=DIGEST, actor_user_id=7,
                provider=provider, send_enabled=a, governed_enabled=b,
                allowed_sucursal_keys=None, session=session, now=NOW,
            )
    session.query.assert_not_called()
    provider.create_campaign.assert_not_called()


def test_new_authorization_does_not_call_provider_and_is_persisted_once():
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    def commit():
        obj = session.add.call_args.args[0]
        obj.id = 41
    session.commit.side_effect = commit
    with patch.object(svc, "_locked_review", return_value=review()), \
         patch.object(svc, "_validate_existing") as validate:
        result = svc.authorize_governed_dispatch(
            campaign_id=99, approval_id=9, expected_digest=DIGEST,
            expected_ready_recipients=5, confirmed=True, actor_user_id=7,
            allowed_sucursal_keys=None, session=session, now=NOW,
        )
    assert result["execution_id"] == 41
    assert result["status"] == "AUTHORIZED"
    assert result["provider_calls"] == 0
    validate.assert_called_once()
    session.commit.assert_called_once()


def test_confirmation_rejected_before_database_io():
    session = MagicMock()
    with pytest.raises(svc.GovernedDispatchConflict):
        svc.authorize_governed_dispatch(
            campaign_id=99, approval_id=9, expected_digest=DIGEST,
            expected_ready_recipients=5, confirmed=False, actor_user_id=7,
            allowed_sucursal_keys=None, session=session, now=NOW,
        )
    session.query.assert_not_called()


def test_execute_claims_one_child_before_network_and_completes():
    e = execution()
    session = fake_authorized_session(e)
    provider = MagicMock()
    provider.create_campaign.return_value = NS(
        provider_campaign_id="synthetic-provider-id",
        deduplicated=False, response_metadata={}, http_status=200,
    )
    claims = []
    def commit():
        claims.append((e.status, session.get.return_value.status))
    # _persist_provider_success is mocked so only two explicit commits occur.
    session.commit.side_effect = commit
    with patch.object(svc, "_locked_review", return_value=review()), \
         patch.object(svc, "_check_child_identities") as identity, \
         patch.object(svc, "build_campaign_v2_provider_dispatch_batch",
                      return_value=NS()) as make_batch, \
         patch.object(svc, "_persist_provider_success") as success:
        result = svc.execute_governed_child(
            campaign_id=99, execution_id=41, child_id=100,
            expected_digest=DIGEST, actor_user_id=7, provider=provider,
            send_enabled=True, governed_enabled=True,
            allowed_sucursal_keys=None, session=session, now=NOW,
        )
    assert result["status"] == "SUBMITTED"
    assert result["execution_status"] == "COMPLETE"
    assert provider.create_campaign.call_count == 1
    assert session.commit.call_count == 2
    assert claims[0][0] == "IN_FLIGHT"
    identity.assert_called_once()
    make_batch.assert_called_once()
    success.assert_called_once()


def test_inflight_execution_blocks_replay_before_provider():
    e = execution("IN_FLIGHT")
    session = fake_authorized_session(e)
    provider = MagicMock()
    with patch.object(svc, "_locked_review", return_value=review()), \
         patch.object(svc, "_check_child_identities") as identity:
        with pytest.raises(svc.GovernedDispatchConflict, match="usada"):
            svc.execute_governed_child(
                campaign_id=99, execution_id=41, child_id=100,
                expected_digest=DIGEST, actor_user_id=7, provider=provider,
                send_enabled=True, governed_enabled=True,
                allowed_sucursal_keys=None, session=session, now=NOW,
            )
    provider.create_campaign.assert_not_called()
    session.commit.assert_not_called()
    identity.assert_not_called()


def test_wrong_child_blocks_before_claim():
    e = execution()
    session = fake_authorized_session(e)
    provider = MagicMock()
    with patch.object(svc, "_locked_review", return_value=review()), \
         patch.object(svc, "_check_child_identities"):
        with pytest.raises(svc.GovernedDispatchConflict, match="siguiente"):
            svc.execute_governed_child(
                campaign_id=99, execution_id=41, child_id=101,
                expected_digest=DIGEST, actor_user_id=7, provider=provider,
                send_enabled=True, governed_enabled=True,
                allowed_sucursal_keys=None, session=session, now=NOW,
            )
    provider.create_campaign.assert_not_called()
    session.commit.assert_not_called()


def test_ambiguous_provider_result_stops_further_execution():
    from app.services.marketing_campaign_v2_provider import CampaignProviderAmbiguousError
    e = execution()
    session = fake_authorized_session(e)
    provider = MagicMock()
    provider.create_campaign.side_effect = CampaignProviderAmbiguousError(
        code="UPSTREAM_UNKNOWN", http_status=500, support_ref="synthetic-only",
    )
    with patch.object(svc, "_locked_review", return_value=review()), \
         patch.object(svc, "_check_child_identities"), \
         patch.object(svc, "build_campaign_v2_provider_dispatch_batch",
                      return_value=NS()), \
         patch.object(svc, "_persist_provider_failure") as fail:
        response = svc.execute_governed_child(
            campaign_id=99, execution_id=41, child_id=100,
            expected_digest=DIGEST, actor_user_id=7, provider=provider,
            send_enabled=True, governed_enabled=True,
            allowed_sucursal_keys=None, session=session, now=NOW,
        )
    assert response["status"] == "RECONCILIATION_REQUIRED"
    assert response["execution_status"] == "REVIEW_REQUIRED"
    assert fail.call_args.kwargs["status"] == "RECONCILIATION_REQUIRED"


def test_expiration_while_waiting_for_lock_stops_before_provider_or_claim():
    e = execution()
    session = fake_authorized_session(e)
    provider = MagicMock()
    after_wait = NOW + timedelta(minutes=20)
    # _locked_review is a stub here, but the clock keeps moving in production.
    # First reading: request arrival. Second reading: after campaign/portfolio locks.
    with patch.object(svc, "_utc", side_effect=[NOW, after_wait]) as clock, \
         patch.object(svc, "_locked_review", return_value=review()), \
         patch.object(svc, "_check_child_identities") as identities:
        with pytest.raises(svc.GovernedDispatchConflict, match="vencida"):
            svc.execute_governed_child(
                campaign_id=99, execution_id=41, child_id=100,
                expected_digest=DIGEST, actor_user_id=7, provider=provider,
                send_enabled=True, governed_enabled=True,
                allowed_sucursal_keys=None, session=session, now=None,
            )
    assert clock.call_count == 2
    identities.assert_not_called()
    provider.create_campaign.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()
