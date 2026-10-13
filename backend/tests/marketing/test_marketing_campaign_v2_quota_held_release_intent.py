"""Issue #856 D3c1: HELD source immutable, fresh quota and no-send intent."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest
from app.services import marketing_campaign_v2_held_release_intent_service as svc

NOW = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
FINGERPRINT = "a" * 64


@dataclass(frozen=True)
class Plan:
    batches: tuple
    ready: bool = True
    mode: str = "IMMEDIATE"
    dispatch_fingerprint: str = "b" * 64


def test_source_requires_unattempted_held_and_completed_execution():
    session = MagicMock()
    campaign, approval, exec_obj, held = (
        NS(id=77),
        NS(id=9, campaign_v2_id=77, template_id=10, approved_at=NOW-timedelta(hours=2),
           dispatch_fingerprint=FINGERPRINT, manifest_json={
               "version": "D2B_READY_HELD_V1", "send_authorized": False,
               "batches": [
                   {"sucursal_canon": "A", "planned_status": "READY"},
                   {"sucursal_canon": "B", "planned_status": "HELD",
                    "hold_evidence": {"source": "test"}},
               ],
           }),
        NS(id=41, approval_id=9, status="COMPLETE"),
        NS(id=100, campaign_v2_id=77, sucursal_canon="B",
           status="HELD", hold_reason="CHANNEL_DAILY_QUOTA",
           hold_evidence_json={"source": "test"}, provider_campaign_id=None,
           submit_started_at=None, submitted_at=None, held_at=NOW,
           held_by_user_id=7, dispatch_fingerprint=FINGERPRINT),
    )
    sent = NS(sucursal_canon="A", status="SUBMITTED",
              provider_campaign_id="synthetic", submitted_at=NOW-timedelta(hours=1))
    def query(model):
        q = MagicMock()
        if model is svc.MarketingCampaignV2ORM:
            q.filter.return_value.one_or_none.return_value = campaign
        elif model is svc.MarketingCampaignV2DispatchApprovalORM:
            q.filter.return_value.one_or_none.return_value = approval
        elif model is svc.MarketingCampaignV2GovernedExecutionORM:
            q.filter.return_value.one_or_none.return_value = exec_obj
        elif model is svc.MarketingCampaignV2ProviderCampaignORM:
            q.filter.return_value.one_or_none.return_value = held
            q.filter.return_value.all.return_value = [sent, held]
        return q
    session.query.side_effect = query
    result = svc._load_source(campaign_id=77, child_id=100, session=session, lock=False)
    assert result[3].status == "HELD"
    assert result[5] == NOW - timedelta(hours=1)
    exec_obj.status = "REVIEW_REQUIRED"
    with pytest.raises(svc.HeldReleaseConflict, match="COMPLETE"):
        svc._load_source(campaign_id=77, child_id=100, session=session, lock=False)
    exec_obj.status = "COMPLETE"
    held.submit_started_at = NOW
    with pytest.raises(svc.HeldReleaseConflict, match="alterado"):
        svc._load_source(campaign_id=77, child_id=100, session=session, lock=False)


def evaluate_context(observed=NOW-timedelta(minutes=5), original_count=5,
                     current_count=5, quota_status="REVIEWABLE"):
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    approval = NS(id=9, template_id=10, approved_at=NOW-timedelta(hours=2),
                  manifest_json={"version":"D2B_READY_HELD_V1","send_authorized":False})
    child = NS(id=100, sucursal_canon="B", recipient_count=original_count,
               channel_binding_id=101, provider_channel_id="channelB",
               request_snapshot_json={"synthetic": True})
    batch = NS(sucursal_canon="B", ready=True, channel_binding_id=101,
               provider_channel_id="channelB", recipients=tuple(range(current_count)))
    plan = Plan(batches=(batch,))
    att = {
        201: NS(id=201, scope_kind="CHANNEL", scope_key="channelB",
                observed_at=observed, expires_at=NOW+timedelta(minutes=10),
                window_ends_at=NOW+timedelta(hours=1)),
        301: NS(id=301, scope_kind="PORTFOLIO", scope_key="shared",
                observed_at=observed, expires_at=NOW+timedelta(minutes=10),
                window_ends_at=NOW+timedelta(hours=1)),
    }
    session.get.side_effect = lambda cls, id: att.get(id)
    quota = {
        "status": quota_status,
        "batches": [{"sucursal_canon":"B", "channel_evidence_id":201,
                     "portfolio_evidence_id":301, "portfolio_key":"shared",
                     "recommendation":"CAPACITY_REVIEWED"}],
    }
    source = (NS(id=77), approval, NS(status="COMPLETE"), child,
              {"planned_status":"HELD", "recipients":original_count},
              NOW-timedelta(hours=1))
    return session, source, plan, quota


def preview(session, source, plan, quota):
    with patch.object(svc, "_load_source", return_value=source), \
         patch.object(svc, "build_campaign_v2_preflight", return_value=plan), \
         patch.object(svc, "build_campaign_v2_provider_dispatch_batch", return_value=NS()), \
         patch.object(svc, "serialize_campaign_v2_provider_request_snapshot",
                      return_value={"synthetic": True}), \
         patch.object(svc, "assess_preflight_capacity", return_value=quota), \
         patch.object(svc, "manifest_digest", return_value=FINGERPRINT):
        return svc.preview_held_release(
            campaign_id=77, child_id=100, allowed_sucursal_keys=None,
            session=session, now=NOW,
        )


def test_preview_only_produces_fingerprint_without_reserving_or_releasing():
    session, source, plan, quota = evaluate_context()
    output = preview(session, source, plan, quota)
    assert output["status"] == "ELIGIBLE_FOR_INTENT_ONLY"
    assert output["recipient_count"] == 5
    assert len(output["candidate_fingerprint"]) == 64
    assert output["quota_reserved"] is False
    assert output["held_released"] is False
    assert output["send_authorized"] is False
    assert "phone" not in str(output).lower()
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.flush.assert_not_called()


def test_quota_must_be_attested_after_original_submission():
    session, source, plan, quota = evaluate_context(
        observed=NOW-timedelta(hours=3),
    )
    with pytest.raises(svc.HeldReleaseConflict, match="posterior"):
        preview(session, source, plan, quota)
    session.add.assert_not_called()


def test_changed_held_population_blocks_preview():
    session, source, plan, quota = evaluate_context(current_count=4)
    with pytest.raises(svc.HeldReleaseConflict, match="volumen"):
        preview(session, source, plan, quota)


def test_missing_fresh_portfolio_capacity_fails_closed():
    session, source, plan, quota = evaluate_context(quota_status="INCOMPLETE")
    with pytest.raises(svc.HeldReleaseConflict, match="cuota NUEVA"):
        preview(session, source, plan, quota)


def test_intent_requires_exact_preview_and_one_request_only():
    session = MagicMock()
    good = {
        "candidate_fingerprint": FINGERPRINT, "recipient_count":5,
        "source_approval_id":9, "source_manifest_digest":"b"*64,
        "evidence":[{"scope_kind":"CHANNEL","attestation_id":201}],
    }
    session.query.return_value.filter.return_value.first.return_value = None
    def assign():
        obj = session.add.call_args.args[0]
        obj.id = 555
    session.commit.side_effect = assign
    args = dict(campaign_id=77, child_id=100, expected_candidate_fingerprint=FINGERPRINT,
                expected_recipient_count=5, source_reference="new quota report",
                reason="Manual follow-up after reset", actor_user_id=7,
                allowed_sucursal_keys=None, session=session, now=NOW)
    with patch.object(svc, "_evaluate", return_value=good):
        result = svc.request_held_release_intent(**args)
    assert result["status"] == "PENDING_FRESH_COHORT"
    assert result["send_authorized"] is False
    session.add.assert_called_once()
    session.commit.assert_called_once()
    obj = session.add.call_args.args[0]
    assert obj.source_child_id == 100 and obj.status == "PENDING_FRESH_COHORT"
    assert obj.evidence_json["quota_reserved"] is False

    other_session = MagicMock()
    other_session.query.return_value.filter.return_value.first.return_value = (555,)
    with patch.object(svc, "_evaluate", return_value=good):
        with pytest.raises(svc.HeldReleaseConflict, match="existe"):
            svc.request_held_release_intent(**(args | {"session":other_session}))
    other_session.commit.assert_not_called()


def test_invalid_digest_and_count_rejected_before_queries():
    session = MagicMock()
    with pytest.raises(svc.HeldReleaseValidation):
        svc.request_held_release_intent(
            campaign_id=77, child_id=100, expected_candidate_fingerprint="bad",
            expected_recipient_count=5, source_reference="report", reason="proof",
            actor_user_id=7, allowed_sucursal_keys=None, session=session,
        )
    session.query.assert_not_called()


def test_module_contains_no_external_provider_or_transition():
    import inspect
    source = inspect.getsource(svc)
    assert "IVentasBroadcastProvider" not in source
    assert "provider.create_campaign(" not in source
    assert "child.status =" not in source


def test_quota_expiring_during_campaign_lock_is_rechecked_with_fresh_clock():
    session, source, plan, quota = evaluate_context()
    after_lock = NOW + timedelta(minutes=20)
    with patch.object(svc, "_load_source", return_value=source), \
         patch.object(svc, "_utc", return_value=after_lock) as clock, \
         patch.object(svc, "build_campaign_v2_preflight", return_value=plan), \
         patch.object(svc, "build_campaign_v2_provider_dispatch_batch", return_value=NS()), \
         patch.object(svc, "serialize_campaign_v2_provider_request_snapshot",
                      return_value={"synthetic": True}), \
         patch.object(svc, "assess_preflight_capacity", return_value=quota), \
         patch.object(svc, "manifest_digest", return_value=FINGERPRINT):
        with pytest.raises(svc.HeldReleaseConflict, match="vigente"):
            svc._evaluate(
                campaign_id=77, child_id=100, allowed_sucursal_keys=None,
                session=session, timestamp=NOW, lock=True,
                refresh_after_lock=True,
            )
    clock.assert_called_once_with(None)
    session.add.assert_not_called()
    session.commit.assert_not_called()
