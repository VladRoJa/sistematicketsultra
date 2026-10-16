"""Fail-closed offline contract for expired and entirely unattempted reauthorization."""
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.services import marketing_campaign_v2_reauthorization_service as svc

NOW = datetime(2026, 10, 16, 18, tzinfo=timezone.utc)
DIGEST = "a" * 64
FINGERPRINT = "f" * 64
QUOTE = "b" * 64


def fixture(monkeypatch, *, execution_status="AUTHORIZED", attempt=False,
            latest_expired=True, revision=1):
    old = NS(
        id=7, campaign_v2_id=22, revision_no=revision, template_id=1,
        expires_at=NOW - timedelta(minutes=6) if latest_expired else NOW + timedelta(minutes=4),
        dispatch_fingerprint=FINGERPRINT, recipient_count=12,
        manifest_json={"version": "D2B_READY_HELD_V1", "basis": "SUITE_BRANCH_EXCEPTION_CAPS_V1",
                       "pricing_currency": "USD", "quote_fingerprint": QUOTE},
    )
    execution = NS(id=7, approval_id=7, status=execution_status, last_child_id=None,
                   expires_at=old.expires_at)
    a = NS(sucursal_canon="A", status="READY", submit_started_at=NOW if attempt else None)
    b = NS(sucursal_canon="B", status="HELD", submit_started_at=None)
    for row in (a, b):
        row.provider_campaign_id = None
        row.submitted_at = None
        row.submitted_by_user_id = None
        row.error_code = None
        row.support_ref = None
        row.provider_response_json = {}
        row.retry_history_json = []
        row.retry_attempt_count = 0

    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    campaign_q, approval_q, execution_q, child_q = (MagicMock() for _ in range(4))
    campaign_q.filter.return_value.with_for_update.return_value.one_or_none.return_value = NS(
        frozen_at=NOW - timedelta(days=1))
    approval_q.filter.return_value.order_by.return_value.with_for_update.return_value.first.return_value = old
    execution_q.filter.return_value.with_for_update.return_value.one_or_none.return_value = execution
    child_q.filter.return_value.order_by.return_value.with_for_update.return_value.all.return_value = [a, b]
    session.query.side_effect = lambda model: {
        svc.Campaign: campaign_q,
        svc.Approval: approval_q,
        svc.Execution: execution_q,
        svc.Child: child_q,
    }[model]
    revised = NS(id=9, revision_no=revision+1, expires_at=NOW+timedelta(minutes=15),
                 manifest_json=old.manifest_json)
    session.get.side_effect = lambda cls, ident: revised if cls == svc.Approval and ident == 9 else None

    def save_execution():
        for call in session.add.call_args_list:
            item = call.args[0]
            if isinstance(item, svc.Execution):
                item.id = 9
    session.flush.side_effect = save_execution

    hold_evidence = {
        "source_reference": "operador-cupo-250", "dispatch_fingerprint": FINGERPRINT,
        "quote_fingerprint": QUOTE,
    }
    definitions = {
        "A": {"planned_status": "READY"},
        "B": {"planned_status": "HELD", "hold_evidence": hold_evidence},
    }
    plan = NS(dispatch_fingerprint=FINGERPRINT, campaign_id=22)
    budget = {"currency": "USD", "quote_fingerprint": QUOTE, "maximum_estimated_usd": "12.0000"}
    quota = {"basis": "SUITE_BRANCH_EXCEPTION_CAPS_V1"}
    scopes = {("CHANNEL", "channel-A"): 5}
    evidence_ids = {("CHANNEL", "channel-A"): None}
    quota_rows = {"A": {"source": "synthetic"}}
    monkeypatch.setattr(svc, "acquire_campaign_v2_contact_gate", lambda _session: None)
    monkeypatch.setattr(svc, "get_campaign_v2", lambda **kw: {"id": kw["campaign_id"]})
    monkeypatch.setattr(svc, "build_campaign_v2_preflight", lambda **kw: plan)
    monkeypatch.setattr(svc, "budget_for_existing_approval", lambda **kw: budget)
    monkeypatch.setattr(svc, "_assert_manifest", lambda *a: definitions)
    validation = MagicMock()
    monkeypatch.setattr(svc, "_validate_existing", validation)
    monkeypatch.setattr(svc, "_ready_plan_and_holds", lambda *a: (plan, {"B"}))
    monkeypatch.setattr(svc, "_assess_scopes",
                        lambda *a, **kw: (quota, scopes, evidence_ids, quota_rows))
    monkeypatch.setattr(svc, "manifest_digest", lambda manifest: DIGEST)
    reserve = MagicMock(return_value={"approval_id": 9, "ready_batches": 1, "held_batches": 1})
    monkeypatch.setattr(svc, "_reserve_locked", reserve)
    return session, reserve, validation, old, execution, a


def invoke(session):
    return svc.reauthorize_unattempted_dispatch(
        campaign_id=22, previous_approval_id=7,
        expected_manifest_digest=DIGEST, actor_user_id=11,
        allowed_sucursal_keys=None, session=session, now=NOW,
    )


def test_unattempted_expired_campaign_creates_fresh_atomic_revision(monkeypatch):
    session, reserve, validate, old, previous_execution, ready = fixture(monkeypatch)
    result = invoke(session)
    assert result["new_approval_id"] == 9
    assert result["new_execution_id"] == 9
    assert result["approval_revision"] == 2
    assert result["ready_batches"] == 1 and result["held_batches"] == 1
    assert result["provider_calls"] == 0 and result["send_authorized"] is False
    assert reserve.call_args.kwargs["commit"] is False
    assert reserve.call_args.kwargs["revision_no"] == 2
    assert reserve.call_args.kwargs["held_evidence_override"]["B"]["source_reference"] == "operador-cupo-250"
    assert validate.call_count == 2
    assert session.commit.call_count == 1
    assert old.id == 7 and previous_execution.status == "AUTHORIZED"
    assert ready.status == "READY" and ready.submit_started_at is None
    assert session.execute.call_count == 1


@pytest.mark.parametrize("status,attempt,expired,reason", [
    ("IN_FLIGHT", False, True, "Solo puede"),
    ("REVIEW_REQUIRED", False, True, "Solo puede"),
    ("COMPLETE", False, True, "Solo puede"),
    ("AUTHORIZED", True, True, "evidencia"),
    ("AUTHORIZED", False, False, "Solo puede"),
])
def test_reauthorization_fails_closed_for_active_or_attempted(monkeypatch, status, attempt, expired, reason):
    session, reserve, _, _, _, _ = fixture(
        monkeypatch, execution_status=status,
        attempt=attempt, latest_expired=expired,
    )
    with pytest.raises(svc.CampaignV2ReauthorizationError, match=reason):
        invoke(session)
    reserve.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_mismatched_stale_approval_cannot_reauthorize(monkeypatch):
    session, reserve, *_ = fixture(monkeypatch)
    with pytest.raises(svc.CampaignV2ReauthorizationError, match="cambió"):
        svc.reauthorize_unattempted_dispatch(
            campaign_id=22, previous_approval_id=6,
            expected_manifest_digest=DIGEST, actor_user_id=11,
            allowed_sucursal_keys=None, session=session, now=NOW,
        )
    reserve.assert_not_called()


def test_invalid_identity_rejected_before_db_access():
    s = MagicMock()
    with pytest.raises(svc.CampaignV2ReauthorizationError):
        svc.reauthorize_unattempted_dispatch(
            campaign_id=22, previous_approval_id=True,
            expected_manifest_digest=DIGEST, actor_user_id=11,
            allowed_sucursal_keys=None, session=s, now=NOW,
        )
    s.query.assert_not_called()


def test_approval_revision_migration_is_additive_and_downgrade_guarded(monkeypatch):
    from alembic.script import ScriptDirectory
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migrations = Path(__file__).resolve().parents[2] / "migrations"
    rev = ScriptDirectory(str(migrations)).get_revision("b856rea1016")
    assert rev.down_revision == "a9c6b2e4f150"
    out = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": out},
    )
    monkeypatch.setattr(rev.module, "op", Operations(ctx))
    rev.module.upgrade()
    sql = out.getvalue()
    assert "revision_no" in sql and "uq_mkt_v2_approval_campaign_revision" in sql
    assert "UPDATE marketing_campaign_v2" not in sql
    assert "DELETE FROM marketing_campaign_v2" not in sql


def test_revision_uniqueness_and_immutable_history_on_real_pg(monkeypatch):
    """Isolated PG16: two revisions allowed, repeated revision denied, rollback guarded."""
    import os
    import sqlalchemy as sa
    from alembic.script import ScriptDirectory
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    raw = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("isolated quota_ci required")
    uri = sa.engine.make_url(raw)
    if (uri.get_backend_name() != "postgresql" or uri.username != "quota_ci"
            or uri.database != "quota_ci" or uri.host not in ("localhost", "127.0.0.1")):
        pytest.fail("Refusing any database except isolated synthetic quota_ci")
    engine = sa.create_engine(raw)
    md = sa.MetaData()
    approvals = sa.Table(
        "marketing_campaign_v2_dispatch_approvals", md,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_v2_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("campaign_v2_id", name="uq_mkt_v2_approval_campaign"),
    )
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    revision = ScriptDirectory(str(migrations)).get_revision("b856rea1016")
    with engine.begin() as conn:
        md.create_all(conn)
        conn.execute(approvals.insert().values(id=7, campaign_v2_id=22))
        monkeypatch.setattr(revision.module, "op",
                            Operations(MigrationContext.configure(conn)))
        revision.module.upgrade()
        conn.execute(sa.text(
            "INSERT INTO marketing_campaign_v2_dispatch_approvals "
            "(id,campaign_v2_id,revision_no) VALUES (9,22,2)"
        ))
        revisions = conn.execute(sa.text(
            "SELECT id, revision_no FROM marketing_campaign_v2_dispatch_approvals "
            "WHERE campaign_v2_id=22 ORDER BY revision_no"
        )).all()
        assert revisions == [(7, 1), (9, 2)]
        with conn.begin_nested():
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text(
                    "INSERT INTO marketing_campaign_v2_dispatch_approvals "
                    "(id,campaign_v2_id,revision_no) VALUES (10,22,2)"
                ))
        with pytest.raises(RuntimeError, match="downgrade destructivo"):
            revision.module.downgrade()
        conn.execute(sa.text(
            "DELETE FROM marketing_campaign_v2_dispatch_approvals WHERE id=9"
        ))
        revision.module.downgrade()
        md.drop_all(conn)
    engine.dispose()
