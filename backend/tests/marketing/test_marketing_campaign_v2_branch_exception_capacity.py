"""Issue 856: no manual cap for standard branches, independent 250 per restricted channel.

No iVentas calls, no send flags, synthetic data only.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from decimal import Decimal

import pytest

from app.services import marketing_campaign_v2_branch_exception_capacity as rules
from app.services import marketing_campaign_v2_dispatch_approval_service as approval
from app.services import marketing_campaign_v2_quota_service as quota_service
from app.services import marketing_campaign_v2_governed_monitor_service as monitor

NOW = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)


def batch(branch, channel, count):
    return NS(sucursal_canon=branch, provider_channel_id=channel,
              template_id=1, recipients=tuple(range(count)))


def plan(*items):
    return NS(ready=True, mode="IMMEDIATE", campaign_id=99,
              dispatch_fingerprint="a" * 64, sendable_phones=tuple(
                  (str(i), str(b.sucursal_canon))
                  for b in items for i in range(len(b.recipients))
              ), batches=tuple(items))


def fake_session(events=(), reservations=()):
    session = MagicMock()
    event_q = MagicMock()
    event_q.filter.return_value.all.return_value = list(events)
    reserved_q = MagicMock()
    reserved_q.join.return_value.filter.return_value.all.return_value = list(reservations)
    session.query.side_effect = [event_q, reserved_q]
    return session


def test_regular_branches_never_need_manual_quota_even_for_large_volume():
    p = plan(batch("AZAHARES_CUL", "chan-az", 100_001))
    db = MagicMock()
    result = rules.assess_branch_exception_capacity(plan=p, session=db, now=NOW)
    assert result["basis"] == rules.BASIS
    assert result["status"] == "REVIEWABLE"
    assert result["reviewed_recipients"] == 100001
    assert result["batches"][0]["restriction_kind"] == "NO_SUITE_DAILY_QUOTA"
    assert result["batches"][0]["operator_channel_cap"] is None
    assert result["send_authorized"] is False
    db.query.assert_not_called()


def test_250_is_separate_per_channel_not_shared_between_branches():
    p = plan(batch("INDEPENDENCIA", "chan-ind", 250),
             batch("INSURGENTES", "chan-ins", 250))
    result = rules.assess_branch_exception_capacity(
        plan=p, session=fake_session(), now=NOW,
    )
    assert result["status"] == "REVIEWABLE"
    assert result["reviewed_recipients"] == 500
    assert [r["operator_channel_cap"] for r in result["batches"]] == [250, 250]
    assert all(r["portfolio_key"] is None for r in result["batches"])


def test_251_or_prior_attempts_or_reservations_blocks_restricted_channel_only():
    evt = NS(provider_channel_id="chan-ind", campaign_v2_id=1,
             status="SUBMITTED", reconciliation_resolution=None,
             submit_started_at=NOW - timedelta(hours=2),
             submitted_at=None, created_at=NOW, recipient_count=248)
    reservation = NS(scope_key="chan-ind", reserved_messages=2)
    p = plan(batch("INDEPENDENCIA", "chan-ind", 1),
             batch("AZAHARES_CUL", "chan-az", 500))
    result = rules.assess_branch_exception_capacity(
        plan=p, session=fake_session([evt], [reservation]), now=NOW,
    )
    assert result["status"] == "INCOMPLETE"
    assert result["batches"][0]["blocking_reason"] == "CHANNEL_EXCEPTION_250_EXCEEDED"
    assert result["batches"][1]["blocking_reason"] is None
    result = rules.assess_branch_exception_capacity(
        plan=plan(batch("INDEPENDENCIA", "chan-ind", 0)), session=fake_session([evt], [reservation]), now=NOW,
    )
    assert result["batches"][0]["blocking_reason"] is None


def test_uncertain_provider_outcome_stays_blocked_even_after_window():
    evt = NS(provider_channel_id="chan-ins", campaign_v2_id=1,
             status="RECONCILIATION_REQUIRED", reconciliation_resolution=None,
             submit_started_at=NOW - timedelta(hours=30),
             submitted_at=None, created_at=NOW, recipient_count=1)
    result = rules.assess_branch_exception_capacity(
        plan=plan(batch("INSURGENTES", "chan-ins", 1)),
        session=fake_session([evt], []), now=NOW,
    )
    assert result["batches"][0]["blocking_reason"] == "UNRESOLVED_PROVIDER_ACTIVITY"


def test_incorrect_channel_is_rejected_for_any_branch():
    p = plan(batch("AZAHARES_CUL", None, 1))
    result = rules.assess_branch_exception_capacity(plan=p, session=MagicMock(), now=NOW)
    assert result["status"] == "INCOMPLETE"
    assert result["batches"][0]["blocking_reason"] == "MISSING_CHANNEL"


def test_existing_approval_basis_is_not_overridden_by_new_mode():
    p = plan(batch("AZAHARES_CUL", "chan-az", 1))
    result = quota_service.assess_preflight_capacity(
        plan=p, session=MagicMock(), now=NOW,
    )
    assert result["basis"] == rules.BASIS
    assert result["status"] == "REVIEWABLE"


def test_channel_only_scope_for_standard_branch_and_exception_mode():
    p = plan(batch("AZAHARES_CUL", "chan-az", 7))
    quota = rules.assess_branch_exception_capacity(plan=p, session=MagicMock(), now=NOW)
    with patch.object(approval, "assess_preflight_capacity", return_value=quota):
        got, quantities, evidence, rows = approval._assess_scopes(
            p, session=MagicMock(), timestamp=NOW,
        )
    assert got["basis"] == rules.BASIS
    assert quantities == {("CHANNEL", "chan-az"): 7}
    assert evidence == {("CHANNEL", "chan-az"): None}
    assert rows["AZAHARES_CUL"]["policy_revision_id"] is None


def test_exceptions_still_need_positive_quota_and_no_manual_bypass():
    p = plan(batch("INDEPENDENCIA", "chan-ind", 251))
    snapshot = rules.assess_branch_exception_capacity(
        plan=p, session=fake_session(), now=NOW,
    )
    with patch.object(approval, "assess_preflight_capacity", return_value=snapshot):
        with pytest.raises(approval.CampaignV2ApprovalConflictError):
            approval._assess_scopes(p, session=MagicMock(), timestamp=NOW)


def test_legacy_reservation_classification_unchanged():
    assert monitor._classify(approval=None, execution=None, children=[],
                             timestamp=NOW) == ("NO_GOVERNED_APPROVAL", None)
