"""Gate A: 26-child durable worker journey with a synthetic provider boundary.

Real PostgreSQL 16, M1a DDL, jobs, worker claims, audit and STOP transitions.
The D2c network boundary is deliberately stubbed: this validates M1c
orchestration, NOT the live iVentas API nor full Angular-to-D2c end-to-end.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.services import marketing_campaign_v2_background_worker_service as worker
from test_background_dispatch_m3_postgres import _migration

FLAGS = {
    "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED": True,
    "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY": True,
    "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED": True,
    "CAMPAIGN_V2_PROVIDER_SEND_ENABLED": True,
}
TOTAL = 26


@pytest.fixture
def durable():
    url = os.getenv("CAMPAIGN_V2_BG_M1A_TEST_PG_URL")
    if not url:
        pytest.skip("Disposable PostgreSQL 16 required")
    parts = sa.engine.make_url(url)
    assert (parts.get_backend_name() == "postgresql"
            and parts.host in ("localhost", "127.0.0.1")
            and parts.database == "quota_ci" and parts.username == "quota_ci")
    schema = "gate_a_" + secrets.token_hex(5)
    administrator = sa.create_engine(url)
    with administrator.begin() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
    engine = sa.create_engine(url, pool_size=3, max_overflow=0)

    # Explicit synthetic schema, never a public-table fallback from SQLAlchemy
    # create_all(checkfirst=True). Apply per connection, including pooled ones.
    @sa.event.listens_for(engine, "connect")
    def _isolate_connection(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET search_path TO {schema}")
        finally:
            cursor.close()
        dbapi_connection.commit()

    try:
        parents = sa.MetaData(schema=schema)
        sa.Table("users", parents, sa.Column("id", sa.Integer, primary_key=True))
        for name in (
            "marketing_campaign_v2_campaigns",
            "marketing_campaign_v2_dispatch_approvals",
            "marketing_campaign_v2_governed_executions",
            "marketing_campaign_v2_provider_campaigns",
        ):
            sa.Table(name, parents, sa.Column("id", sa.BigInteger, primary_key=True))
        parents.create_all(engine)
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users(id) VALUES (1)"))
            for name in ("marketing_campaign_v2_campaigns",
                         "marketing_campaign_v2_dispatch_approvals",
                         "marketing_campaign_v2_governed_executions"):
                conn.execute(sa.text(f"INSERT INTO {name}(id) VALUES (1)"))
            conn.execute(sa.text(
                "INSERT INTO marketing_campaign_v2_provider_campaigns(id) "
                "SELECT generate_series(1, 26)"
            ))
            m = _migration()
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            m.op = Operations(MigrationContext.configure(conn))
            m.upgrade()
            pending = list(range(1, TOTAL + 1))
            digest = hashlib.sha256(
                json.dumps(pending, separators=(",", ":")).encode("ascii")
            ).hexdigest()
            conn.execute(sa.text("""
                INSERT INTO marketing_campaign_v2_background_jobs
                  (id, campaign_v2_id, approval_id, execution_id, operator_user_id,
                   request_key, manifest_digest, pending_child_ids,
                   pending_children_digest, initial_pending_count, start_deadline_at)
                VALUES (50, 1, 1, 1, 1,
                        :key, :manifest, CAST(:ids AS json),
                        :digest, 26, now()+interval '10 minutes')
            """), {"key": "a" * 64, "manifest": "b" * 64,
                   "ids": json.dumps(pending), "digest": digest})
            conn.execute(sa.text("""
                INSERT INTO marketing_campaign_v2_background_job_events
                  (job_id, event_no, event_kind)
                VALUES (50, 1, 'ENQUEUED')
            """))
        with engine.connect() as conn:
            assert int(conn.scalar(sa.text("SHOW server_version_num"))) >= 160000
            assert conn.scalar(sa.text("SELECT count(*) FROM marketing_campaign_v2_background_jobs")) == 1
        yield engine
    finally:
        engine.dispose()
        with administrator.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        administrator.dispose()


class FakeChildrenSession(Session):
    """Only the unrelated provider child representation is faked.

    The JobORM, EventORM and all job transitions use real PostgreSQL.
    """
    def __init__(self, *args, children, **kwargs):
        super().__init__(*args, **kwargs)
        self.children = children

    def get(self, entity, ident, **kwargs):
        if entity is worker.Child:
            return self.children[int(ident)]
        return super().get(entity, ident, **kwargs)


@pytest.mark.parametrize("scenario,expected_count,expected_status", [
    ("all", 26, "COMPLETED"),
    ("stop_after_7", 7, "STOPPED"),
    ("ambiguous_after_4", 4, "REVIEW_REQUIRED"),
])
def test_durable_26_child_pipeline_with_mock_provider(
    durable, scenario, expected_count, expected_status,
):
    engine = durable
    children = {
        ident: SimpleNamespace(id=ident, campaign_v2_id=1,
            status="READY", submit_started_at=None,
            provider_campaign_id=None, submitted_at=None)
        for ident in range(1, TOTAL + 1)
    }
    calls = []
    provider_factory_calls = []

    def fake_d2c(*, campaign_id, execution_id, child_id, expected_digest,
                 actor_user_id, provider, background_claim,
                 allowed_sucursal_keys, send_enabled, governed_enabled, session):
        assert (campaign_id, execution_id, actor_user_id) == (1, 1, 1)
        assert expected_digest == "b" * 64
        assert (background_claim.job_id, background_claim.worker_instance_id,
                background_claim.worker_claim_generation) == (50, "worker-A", 1)
        assert send_enabled and governed_enabled
        assert allowed_sucursal_keys is None
        assert child_id == len(calls) + 1
        assert children[child_id].status == "READY"
        calls.append(child_id)
        if scenario == "ambiguous_after_4" and len(calls) == 4:
            return {"status": "RECONCILIATION_REQUIRED", "child_id": child_id}
        children[child_id].status = "SUBMITTED"
        children[child_id].provider_campaign_id = "synthetic-" + str(child_id)
        children[child_id].submitted_at = datetime.now(timezone.utc)
        if scenario == "stop_after_7" and len(calls) == 7:
            # Independent operator STOP after last successful provider response.
            with engine.begin() as conn:
                conn.execute(sa.text("""
                    UPDATE marketing_campaign_v2_background_jobs
                       SET status='STOP_REQUESTED',
                           stop_requested_at=now()
                     WHERE id=50 AND status='RUNNING'
                """))
        return {"status": "SUBMITTED", "child_id": child_id}

    def fake_provider_factory():
        provider_factory_calls.append(True)
        return object()

    with patch.object(worker, "_actor"), patch.object(
            worker, "execute_governed_child", side_effect=fake_d2c):
        with Session(engine) as session:
            claim = worker.claim_next_queued(
                session=session, worker_id="worker-A", config=FLAGS)
            assert claim == (50, 1)
        with Session(engine) as other:
            assert worker.claim_next_queued(
                session=other, worker_id="worker-B", config=FLAGS) is None
        with FakeChildrenSession(engine, children=children) as session:
            worker.process_claimed_job(
                session=session, job_id=50, worker_id="worker-A",
                generation=1, config=FLAGS, provider_factory=fake_provider_factory)

        assert calls == list(range(1, expected_count + 1))
        assert len(provider_factory_calls) == expected_count

        with engine.connect() as conn:
            row = conn.execute(sa.text("""
                SELECT status, worker_claim_generation, last_accepted_child_id
                  FROM marketing_campaign_v2_background_jobs WHERE id=50
            """)).one()
            assert row.status == expected_status
            assert row.worker_claim_generation == 1
            assert row.last_accepted_child_id == (
                expected_count if scenario != "ambiguous_after_4" else 3)
            n_accepted = conn.scalar(sa.text("""
                SELECT count(*) FROM marketing_campaign_v2_background_job_events
                 WHERE job_id=50 AND event_kind='CHILD_ACCEPTED'
            """))
            assert n_accepted == (expected_count if scenario != "ambiguous_after_4"
                                  else expected_count - 1)
            reasons = [v[0] for v in conn.execute(sa.text("""
                SELECT event_kind FROM marketing_campaign_v2_background_job_events
                 WHERE job_id=50 ORDER BY event_no
            """))]
            assert reasons[0:2] == ["ENQUEUED", "STARTED"]
            assert reasons[-1] == expected_status
            assert reasons.count("STARTED") == 1

        # Never resume a completed, stopped or ambiguous job automatically.
        with FakeChildrenSession(engine, children=children) as session:
            worker.process_claimed_job(
                session=session, job_id=50, worker_id="worker-A",
                generation=1, config=FLAGS, provider_factory=fake_provider_factory)
        assert len(calls) == expected_count

def test_unexpected_worker_boundary_failure_never_replays(durable):
    """An unexpected D2c boundary exception quarantines the mandate without retry.

    This is a synthetic worker-boundary test, not a real 502/iVentas test.
    """
    engine = durable
    children = {
        ident: SimpleNamespace(
            id=ident, campaign_v2_id=1, status="READY",
            submit_started_at=None, provider_campaign_id=None, submitted_at=None,
        )
        for ident in range(1, TOTAL + 1)
    }
    provider_factory_calls = []
    d2c_calls = []

    def failed_d2c(**kwargs):
        d2c_calls.append(kwargs["child_id"])
        raise RuntimeError("SYNTHETIC_PROVIDER_BOUNDARY_FAILURE")

    def provider_factory():
        provider_factory_calls.append(True)
        return object()

    with patch.object(worker, "_actor"), patch.object(
        worker, "execute_governed_child", side_effect=failed_d2c,
    ):
        with Session(engine) as session:
            assert worker.claim_next_queued(
                session=session, worker_id="worker-A", config=FLAGS,
            ) == (50, 1)

        with FakeChildrenSession(engine, children=children) as session:
            with pytest.raises(RuntimeError, match="SYNTHETIC_PROVIDER_BOUNDARY_FAILURE"):
                worker.process_claimed_job(
                    session=session, job_id=50, worker_id="worker-A",
                    generation=1, config=FLAGS, provider_factory=provider_factory,
                )

        with engine.connect() as conn:
            job = conn.execute(sa.text("""
                SELECT status, current_child_id, last_accepted_child_id,
                       worker_lease_until, stop_reason_code
                  FROM marketing_campaign_v2_background_jobs WHERE id=50
            """)).one()
            assert job.status == "REVIEW_REQUIRED"
            assert job.current_child_id == 1  # retain reconciliation evidence
            assert job.last_accepted_child_id is None
            assert job.worker_lease_until is None
            assert job.stop_reason_code == "UNEXPECTED_WORKER_FAILURE"
            events = [row[0] for row in conn.execute(sa.text("""
                SELECT event_kind FROM marketing_campaign_v2_background_job_events
                 WHERE job_id=50 ORDER BY event_no
            """))]
            assert events == ["ENQUEUED", "STARTED", "REVIEW_REQUIRED"]

        # A different worker cannot claim the quarantined job.
        with Session(engine) as session:
            assert worker.claim_next_queued(
                session=session, worker_id="worker-B", config=FLAGS,
            ) is None

        # Neither the original worker nor the new one may trigger a second D2c call.
        with FakeChildrenSession(engine, children=children) as session:
            worker.process_claimed_job(
                session=session, job_id=50, worker_id="worker-A",
                generation=1, config=FLAGS, provider_factory=provider_factory,
            )
        assert d2c_calls == [1]
        assert len(provider_factory_calls) == 1
