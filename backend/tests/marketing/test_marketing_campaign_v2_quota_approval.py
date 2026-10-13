"""D2a: synthetic tests for conservative campaign approval reservations."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest
from app.services import marketing_campaign_v2_dispatch_approval_service as approval

NOW = datetime(2026, 10, 13, 17, tzinfo=timezone.utc)
FP = "a" * 64
QF = "b" * 64


def test_confirmation_is_exact_not_float():
    assert approval._validate_confirmation(FP, QF, 12, "3.60", 7) == (
        FP, QF, 12, Decimal("3.60"), 7,
    )
    for args in [(FP, QF, True, "3.60", 7), (FP, QF, 12, 3.6, 7),
                 (FP, QF, 12, "NaN", 7), ("wrong", QF, 12, "3.60", 7),
                 (FP, QF, 0, "3.60", 7), (FP, QF, 12, "3.6", 7),
                 (FP, "not-a-quote", 12, "3.60", 7)]:
        with pytest.raises(approval.CampaignV2ApprovalValidationError):
            approval._validate_confirmation(*args)


def test_sqlite_cannot_claim_transactional_reservation():
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "sqlite"
    with pytest.raises(approval.CampaignV2ApprovalConflictError, match="PostgreSQL"):
        approval.approve_dispatch_reservation(
            campaign_id=1, template_id=2,
            expected_dispatch_fingerprint=FP,
            expected_quote_fingerprint=QF,
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


def reservation_fixture(already_reserved=0):
    p = NS(campaign_id=99, mode="IMMEDIATE", ready=True,
           dispatch_fingerprint=FP,
           sendable_phones=[str(x) for x in range(12)],
           batches=[NS(sucursal_canon="A", provider_channel_id="ch1",
                       template_id=2, recipients=[None] * 12)])
    budget = {
        "status": "COMPLETE", "currency": "MXN", "sendable_recipients": 12,
        "total_estimated_mxn": "3.60", "quote_fingerprint": QF,
        "batches": [{"sucursal_canon": "A", "recipients": 12,
                     "revision_id": 11, "estimated_mxn": "3.60"}],
    }
    quota_rows = {"A": {"channel_evidence_id": 1,
                        "portfolio_attestation_id": 3,
                        "portfolio_key": "shared",
                        "portfolio_evidence_id": 3}}
    quantities = {("PORTFOLIO", "shared"): 12}
    ids = {("PORTFOLIO", "shared"): 3}
    session = MagicMock()
    session.get.return_value = NS(
        id=3, scope_kind="PORTFOLIO", scope_key="shared",
        observed_at=NOW-timedelta(minutes=2),
        expires_at=NOW+timedelta(minutes=12),
        window_ends_at=NOW+timedelta(hours=6),
        remaining_messages=12,
    )
    session.query.return_value.filter.return_value.scalar.return_value = already_reserved

    def flush():
        for call in session.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, approval.MarketingCampaignV2DispatchApprovalORM):
                obj.id = 42
    session.flush.side_effect = flush
    return p, budget, quota_rows, quantities, ids, session


def test_active_reservation_is_subtracted_even_with_new_evidence_revision():
    p, budget, rows, quantities, ids, session = reservation_fixture(already_reserved=1)
    with pytest.raises(approval.CampaignV2ApprovalConflictError, match="remanente"):
        approval._reserve_locked(
            plan=p, budget=budget, confirmation=(FP, QF, 12, Decimal("3.60"), 7),
            session=session, timestamp=NOW, quantities=quantities,
            evidence_ids=ids, quota_rows=rows,
        )
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_success_is_reservation_only_and_expires_with_attestation():
    p, budget, rows, quantities, ids, session = reservation_fixture()
    result = approval._reserve_locked(
        plan=p, budget=budget, confirmation=(FP, QF, 12, Decimal("3.60"), 7),
        session=session, timestamp=NOW, quantities=quantities,
        evidence_ids=ids, quota_rows=rows,
    )
    assert result["send_authorized"] is False
    assert result["status"] == "RESERVED_NOT_DISPATCHED"
    assert result["expires_at"] == (NOW+timedelta(minutes=12)).isoformat()
    assert result["manifest"]["batches"][0]["planned_status"] == "READY"
    assert session.add.call_count == 2
    session.commit.assert_called_once()


def test_migration_revision_linear_and_ledger_sql(monkeypatch):
    from io import StringIO
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    migrations = Path(__file__).resolve().parents[2] / "migrations"
    rev = ScriptDirectory(str(migrations)).get_revision("a856d2a01013")
    assert rev.down_revision == "f4d856a1b20c"
    out = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": out},
    )
    monkeypatch.setattr(rev.module, "op", Operations(ctx))
    rev.module.upgrade()
    sql = out.getvalue()
    assert "marketing_campaign_v2_dispatch_approvals" in sql
    assert "marketing_campaign_v2_capacity_reservations" in sql
    assert "uq_mkt_v2_approval_campaign" in sql
    assert "reserved_messages > 0" in sql
