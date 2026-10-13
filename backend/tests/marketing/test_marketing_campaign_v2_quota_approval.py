"""D2a: synthetic tests for conservative campaign approval reservations."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest
from app.services import marketing_campaign_v2_dispatch_approval_service as approval

NOW = datetime(2026, 10, 13, 17, tzinfo=timezone.utc)
FP = "a" * 64


def test_confirmation_is_exact_not_float():
    assert approval._validate_confirmation(FP, 12, "3.60", 7) == (
        FP, 12, Decimal("3.60"), 7,
    )
    for args in [(FP, True, "3.60", 7), (FP, 12, 3.6, 7),
                 (FP, 12, "NaN", 7), ("wrong", 12, "3.60", 7),
                 (FP, 0, "3.60", 7), (FP, 12, "3.6", 7)]:
        with pytest.raises(approval.CampaignV2ApprovalValidationError):
            approval._validate_confirmation(*args)


def test_sqlite_cannot_claim_transactional_reservation():
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "sqlite"
    with pytest.raises(approval.CampaignV2ApprovalConflictError, match="PostgreSQL"):
        approval.approve_dispatch_reservation(
            campaign_id=1, template_id=2,
            expected_dispatch_fingerprint=FP,
            expected_recipients=12, expected_total_mxn="3.60",
            actor_user_id=7, allowed_sucursal_keys=None,
            session=session, now=NOW,
        )
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_shared_portfolio_is_aggregated_before_reservation():
    batches = (
        NS(sucursal_canon="A", provider_channel_id="ch1", recipients=[None] * 5),
        NS(sucursal_canon="B", provider_channel_id="ch2", recipients=[None] * 7),
    )
    plan = NS(ready=True, mode="IMMEDIATE", batches=batches)
    response = {
        "status": "REVIEWABLE",
        "batches": [
            {"sucursal_canon": "A", "provider_channel_id": "ch1",
             "portfolio_key": "shared", "channel_evidence_id": 1,
             "portfolio_evidence_id": 3, "recommendation": "CAPACITY_REVIEWED"},
            {"sucursal_canon": "B", "provider_channel_id": "ch2",
             "portfolio_key": "shared", "channel_evidence_id": 2,
             "portfolio_evidence_id": 3, "recommendation": "CAPACITY_REVIEWED"},
        ],
    }
    with patch.object(approval, "assess_preflight_capacity", return_value=response):
        _, quantities, evidence_ids, _ = approval._assess_scopes(
            plan, session=MagicMock(), timestamp=NOW,
        )
    assert quantities == {
        ("CHANNEL", "ch1"): 5, ("CHANNEL", "ch2"): 7,
        ("PORTFOLIO", "shared"): 12,
    }
    assert evidence_ids[("PORTFOLIO", "shared")] == 3


def test_unverified_or_partial_capacity_does_not_approve():
    plan = NS(ready=True, mode="IMMEDIATE", batches=[
        NS(sucursal_canon="A", provider_channel_id="ch1", recipients=[None]),
    ])
    with patch.object(approval, "assess_preflight_capacity",
                      return_value={"status": "INCOMPLETE", "batches": []}):
        with pytest.raises(approval.CampaignV2ApprovalConflictError):
            approval._assess_scopes(plan, session=MagicMock(), timestamp=NOW)
