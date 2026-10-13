"""D3b — explicitly manual, atomic reconciliation with no provider dependency."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
import pytest

from app.services import marketing_campaign_v2_governed_reconciliation_service as svc

NOW = datetime(2026, 10, 13, 20, tzinfo=timezone.utc)
DIGEST = "a"*64


def context(child_status="SUBMITTING", exec_status="IN_FLIGHT",
            age_minutes=11, actual_campaign_id=77):
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    approval = NS(id=9, campaign_v2_id=actual_campaign_id,
                  manifest_json={"version": "D2B_READY_HELD_V1"})
    execution = NS(
        id=41, approval_id=9, last_child_id=100,
        status=exec_status, manifest_digest=DIGEST,
        updated_at=NOW-timedelta(minutes=age_minutes),
    )
    child = NS(
        id=100, campaign_v2_id=actual_campaign_id,
        status=child_status, provider="IVENTAS",
        provider_campaign_id=None, error_code=None, support_ref="support-old",
        reconciliation_resolution=None, retry_next_allowed_at=None,
        reconciliation_snapshot_json={}, reconciled_at=None,
        submitted_at=None, updated_at=NOW,
    )
    def get(model, identifier):
        if model is svc.MarketingCampaignV2GovernedExecutionORM:
            return execution
        if model is svc.MarketingCampaignV2DispatchApprovalORM:
            return approval
        raise AssertionError("Unknown get")
    session.get.side_effect = get
    def query(model):
        q = MagicMock()
        if model is svc.MarketingCampaignV2ORM:
            q.filter.return_value.with_for_update.return_value.one_or_none.return_value = NS(id=77)
        elif model is svc.MarketingCampaignV2DispatchApprovalORM:
            q.filter.return_value.with_for_update.return_value.one_or_none.return_value = approval
        elif model is svc.MarketingCampaignV2GovernedExecutionORM:
            q.filter.return_value.with_for_update.return_value.one_or_none.return_value = execution
        elif model is svc.MarketingCampaignV2ProviderCampaignORM:
            q.filter.return_value.with_for_update.return_value.one_or_none.return_value = child
            q.filter.return_value.first.return_value = None
        else:
            raise AssertionError("Unexpected model")
        return q
    session.query.side_effect = query
    return session, execution, child


def common():
    return dict(campaign_id=77, execution_id=41, child_id=100,
                expected_manifest_digest=DIGEST, actor_user_id=7,
                source_reference="synthetic provider ticket ref",
                evidence_note="Operador verificó historial, sin disparar ninguna campaña.")


def test_stale_unknown_claim_escalates_atomically_without_provider():
    session, execution, child = context()
    with patch.object(svc, "manifest_digest", return_value=DIGEST):
        result = svc.escalate_stale_governed_claim(
            **common(), session=session, now=NOW,
        )
    assert result["provider_outcome"] == "UNKNOWN"
    assert result["may_auto_retry"] is False
    assert execution.status == "REVIEW_REQUIRED"
    assert child.status == "RECONCILIATION_REQUIRED"
    assert child.error_code == "GOVERNED_UNCERTAIN_OUTCOME"
    audit = session.add.call_args.args[0]
    assert audit.event_kind == "STALE_CLAIM_REVIEW"
    assert audit.previous_child_status == "SUBMITTING"
    assert audit.next_child_status == "RECONCILIATION_REQUIRED"
    assert audit.previous_execution_status == "IN_FLIGHT"
    assert audit.next_execution_status == "REVIEW_REQUIRED"
    session.commit.assert_called_once()


def test_recent_claim_cannot_be_escalated_even_by_authorized_operator():
    session, execution, child = context(age_minutes=3)
    with patch.object(svc, "manifest_digest", return_value=DIGEST):
        with pytest.raises(svc.GovernedReconciliationConflict, match="aún"):
            svc.escalate_stale_governed_claim(
                **common(), session=session, now=NOW,
            )
    assert execution.status == "IN_FLIGHT"
    assert child.status == "SUBMITTING"
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_wrong_campaign_cannot_be_reconciled():
    session, _, _ = context(actual_campaign_id=88)
    with pytest.raises(svc.GovernedReconciliationConflict, match="no coinciden"):
        svc.escalate_stale_governed_claim(
            **common(), session=session, now=NOW,
        )
    session.commit.assert_not_called()


def test_stale_already_submitted_is_not_rewritten():
    session, execution, child = context(child_status="SUBMITTED")
    child.provider_campaign_id = "already-accepted"
    with patch.object(svc, "manifest_digest", return_value=DIGEST):
        result = svc.escalate_stale_governed_claim(**common(), session=session, now=NOW)
    assert result["child_status"] == "SUBMITTED"
    assert child.provider_campaign_id == "already-accepted"
    assert execution.status == "REVIEW_REQUIRED"


def test_manual_found_records_provider_identity_and_never_unlocks():
    session, execution, child = context(child_status="RECONCILIATION_REQUIRED",
                                        exec_status="REVIEW_REQUIRED")
    with patch.object(svc, "manifest_digest", return_value=DIGEST):
        result = svc.record_governed_provider_resolution(
            **common(), resolution="PROVIDER_CAMPAIGN_FOUND",
            provider_campaign_id="synthetic-provider-id", session=session, now=NOW,
        )
    assert result["child_status"] == "SUBMITTED"
    assert result["execution_status"] == "REVIEW_REQUIRED"
    assert result["send_authorized"] is False
    assert child.provider_campaign_id == "synthetic-provider-id"
    assert child.reconciliation_resolution == "PROVIDER_CAMPAIGN_FOUND"
    assert child.reconciliation_snapshot_json["provider_actual_acceptance_time"] == "UNVERIFIED"
    audit = session.add.call_args.args[0]
    assert audit.event_kind == "PROVIDER_CAMPAIGN_FOUND"
    assert audit.provider_campaign_id == "synthetic-provider-id"
    session.commit.assert_called_once()


def test_manual_not_created_remains_non_retryable():
    session, execution, child = context(child_status="RECONCILIATION_REQUIRED",
                                        exec_status="REVIEW_REQUIRED")
    with patch.object(svc, "manifest_digest", return_value=DIGEST):
        result = svc.record_governed_provider_resolution(
            **common(), resolution="NOT_CREATED_CONFIRMED",
            session=session, now=NOW,
        )
    assert result["may_auto_retry"] is False
    assert child.status == "PROVIDER_ERROR"
    assert child.retry_next_allowed_at is None
    assert child.provider_campaign_id is None
    assert execution.status == "REVIEW_REQUIRED"
    session.commit.assert_called_once()


def test_resolution_rejected_without_manual_escalation():
    session, _, _ = context(child_status="SUBMITTING", exec_status="IN_FLIGHT")
    with patch.object(svc, "manifest_digest", return_value=DIGEST):
        with pytest.raises(svc.GovernedReconciliationConflict, match="no permite"):
            svc.record_governed_provider_resolution(
                **common(), resolution="NOT_CREATED_CONFIRMED",
                session=session, now=NOW,
            )
    session.commit.assert_not_called()


@pytest.mark.parametrize("resolution,provider_id", [
    ("UNKNOWN", None), ("PROVIDER_CAMPAIGN_FOUND", None),
    ("NOT_CREATED_CONFIRMED", "forbidden"),
])
def test_invalid_resolution_or_identity_fails_before_db(resolution, provider_id):
    session = MagicMock()
    with pytest.raises(svc.GovernedReconciliationValidation):
        svc.record_governed_provider_resolution(
            **common(), resolution=resolution,
            provider_campaign_id=provider_id, session=session, now=NOW,
        )
    session.get.assert_not_called()
    session.commit.assert_not_called()


def test_governed_reconciliation_source_never_invokes_provider():
    import inspect
    source = inspect.getsource(svc)
    assert "provider.create_campaign" not in source
    assert "IVentasBroadcastProvider" not in source
