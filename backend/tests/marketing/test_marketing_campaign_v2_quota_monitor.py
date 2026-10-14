"""D3a read-only monitoring: no sends, no DML and explicit operator review."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import pytest

from app.services import marketing_campaign_v2_governed_monitor_service as svc

NOW = datetime(2026, 10, 13, 19, tzinfo=timezone.utc)


def fake_rows(*, execution_status="IN_FLIGHT", updated_minutes=7, expires_minutes=10):
    approval = NS(
        id=9, campaign_v2_id=77, approved_at=NOW-timedelta(minutes=5),
        expires_at=NOW+timedelta(minutes=expires_minutes),
        dispatch_fingerprint="a"*64, manifest_json={"version": "D2B_READY_HELD_V1"},
    )
    execution = NS(
        id=41, approval_id=9, status=execution_status, last_child_id=100,
        confirmed_at=NOW-timedelta(minutes=9),
        expires_at=approval.expires_at,
        updated_at=NOW-timedelta(minutes=updated_minutes),
    )
    ready = NS(
        id=100, sucursal_canon="A", provider_channel_id="ch1",
        recipient_count=5, status="SUBMITTING", provider_campaign_id=None,
        idempotency_key="b"*64, hold_reason=None, held_at=None,
        submit_started_at=NOW-timedelta(minutes=updated_minutes),
        submitted_at=None, error_code=None, support_ref=None,
        reconciliation_resolution=None, reconciled_at=None,
    )
    held = NS(
        id=101, sucursal_canon="B", provider_channel_id="ch2",
        recipient_count=7, status="HELD", provider_campaign_id=None,
        idempotency_key="c"*64, hold_reason="CHANNEL_DAILY_QUOTA",
        held_at=NOW-timedelta(minutes=10), submit_started_at=None,
        submitted_at=None, error_code=None, support_ref=None,
        reconciliation_resolution=None, reconciled_at=None,
    )
    reservation = NS(
        scope_kind="PORTFOLIO", scope_key="shared",
        reserved_messages=5, attestation_id=3,
        reserved_until=NOW+timedelta(minutes=expires_minutes),
    )
    evidence = NS(
        expires_at=NOW+timedelta(minutes=expires_minutes),
        window_ends_at=NOW+timedelta(hours=2),
        observed_at=NOW-timedelta(minutes=15),
    )
    return approval, execution, [ready, held], [reservation], evidence


def fake_session(*, execution_status="IN_FLIGHT", updated_minutes=7,
                 expires_minutes=10, operator_mode=False):
    approval, execution, children, reserves, evidence = fake_rows(
        execution_status=execution_status, updated_minutes=updated_minutes,
        expires_minutes=expires_minutes,
    )
    if operator_mode:
        approval.manifest_json["basis"] = "SUITE_OPERATOR_ROLLING_24H_V1"
        reserves[0].attestation_id = None
    session = MagicMock()
    def get(model, identifier):
        if model is svc.MarketingCampaignV2ORM:
            return NS(id=77)
        if model is svc.MarketingCampaignV2QuotaCapacityAttestationORM:
            return evidence if identifier == 3 else None
        raise AssertionError("Unexpected get model")
    session.get.side_effect = get

    def query(model):
        q = MagicMock()
        filter_q = q.filter.return_value
        if model is svc.MarketingCampaignV2DispatchApprovalORM:
            filter_q.one_or_none.return_value = approval
        elif model is svc.MarketingCampaignV2GovernedExecutionORM:
            filter_q.one_or_none.return_value = execution
        elif model is svc.MarketingCampaignV2CapacityReservationORM:
            filter_q.order_by.return_value.all.return_value = reserves
        elif model is svc.MarketingCampaignV2ProviderCampaignORM:
            filter_q.order_by.return_value.all.return_value = children
        else:
            raise AssertionError("Unexpected query")
        return q
    session.query.side_effect = query
    return session


def test_inflight_stale_never_resends_or_writes():
    session = fake_session()
    result = svc.read_governed_dispatch_monitor(
        campaign_id=77, session=session, now=NOW,
    )
    assert result["status"] == "IN_FLIGHT_STALE"
    assert result["next_manual_action"] == "VERIFY_PROVIDER_OUTCOME_MANUALLY"
    assert result["children_by_status"] == {"SUBMITTING": 1, "HELD": 1}
    assert result["children"][0]["needs_manual_review"] is True
    assert result["children"][1]["needs_manual_review"] is False
    assert result["quota"]["all_current"] is True
    assert result["send_authorized"] is False
    assert result["may_auto_retry"] is False
    assert result["may_auto_release_held"] is False
    session.commit.assert_not_called()
    session.add.assert_not_called()
    session.execute.assert_not_called()
    session.flush.assert_not_called()


def test_recent_inflight_is_not_misclassified_as_stale():
    session = fake_session(updated_minutes=2)
    result = svc.read_governed_dispatch_monitor(campaign_id=77, session=session, now=NOW)
    assert result["status"] == "IN_FLIGHT"
    assert result["next_manual_action"] == "DO_NOT_RESEND"


def test_expired_quota_is_not_marked_current():
    session = fake_session(execution_status="AUTHORIZED", expires_minutes=-1)
    result = svc.read_governed_dispatch_monitor(campaign_id=77, session=session, now=NOW)
    assert result["quota"]["all_current"] is False
    assert result["quota"]["reservations"][0]["is_current"] is False
    assert result["approval"]["expired"] is True
    assert result["status"] == "RECONCILIATION_REQUIRED"  # child SUBMITTING never ignored
    session.commit.assert_not_called()


def test_review_required_does_not_turn_into_retry_permission():
    session = fake_session(execution_status="REVIEW_REQUIRED")
    result = svc.read_governed_dispatch_monitor(campaign_id=77, session=session, now=NOW)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["may_auto_retry"] is False
    assert result["execution"]["status"] == "REVIEW_REQUIRED"


def test_classification_of_expired_prepared_approval():
    approval = NS(expires_at=NOW-timedelta(seconds=1))
    status, action = svc._classify(approval=approval, execution=None,
                                  children=[], timestamp=NOW)
    assert status == "APPROVAL_EXPIRED"
    assert action == "NEW_AUTHORIZATION_POLICY_REQUIRED"


def test_invalid_date_and_id_fail_closed():
    with pytest.raises(svc.GovernedMonitorValidation):
        svc.read_governed_dispatch_monitor(campaign_id=True, session=MagicMock())
    with pytest.raises(svc.GovernedMonitorValidation):
        svc._now_utc(datetime(2026, 10, 13, 12, 0))


def test_operator_only_lease_never_dereferences_null_attestation():
    session = fake_session(operator_mode=True)
    result = svc.read_governed_dispatch_monitor(campaign_id=77, session=session, now=NOW)
    assert result["quota"]["basis"] == "SUITE_OPERATOR_ROLLING_24H_V1"
    assert result["quota"]["reservations"][0]["attestation_id"] is None
    assert result["quota"]["reservations"][0]["attestation_expires_at"] is None
    assert result["quota"]["all_current"] is True
    assert "NOT_META_VERIFIED" in result["basis"]
    assert session.get.call_count == 1  # campaign only, no phantom Meta attestation
    session.commit.assert_not_called()


def test_operator_only_expired_lease_is_not_current():
    session = fake_session(operator_mode=True, expires_minutes=-1)
    result = svc.read_governed_dispatch_monitor(campaign_id=77, session=session, now=NOW)
    assert result["quota"]["all_current"] is False
    assert result["quota"]["reservations"][0]["is_current"] is False
