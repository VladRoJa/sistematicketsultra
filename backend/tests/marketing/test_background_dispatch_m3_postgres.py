"""Issue #1129 M3: PostgreSQL 16 schema/claim safety on an EPHEMERAL CI DB.

No real campaigns, no provider calls. Refuses nonlocal/non-synthetic URLs.
This test runs after other PG suites and intentionally keeps its synthetic rows:
GitHub Actions destroys the entire postgres:16 service after the job.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services import marketing_campaign_v2_background_worker_service as worker

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/versions/n26c10202626_campaign_v2_background_jobs.py"


def _engine():
    url = os.getenv("CAMPAIGN_V2_BG_M1A_TEST_PG_URL")
    if not url:
        pytest.skip("Requires a disposable PostgreSQL 16 service in CI")
    parts = sa.engine.make_url(url)
    assert parts.get_backend_name() == "postgresql"
    assert parts.host in ("127.0.0.1", "localhost")
    assert parts.database == "quota_ci" and parts.username == "quota_ci"
    return sa.create_engine(url, pool_size=2, max_overflow=0)


def _migration():
    spec = importlib.util.spec_from_file_location("issue1129_m3_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parents(engine):
    meta = sa.MetaData()
    sa.Table("users", meta, sa.Column("id", sa.Integer, primary_key=True))
    for name in (
        "marketing_campaign_v2_campaigns",
        "marketing_campaign_v2_dispatch_approvals",
        "marketing_campaign_v2_governed_executions",
        "marketing_campaign_v2_provider_campaigns",
    ):
        sa.Table(name, meta, sa.Column("id", sa.BigInteger, primary_key=True))
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO users(id) VALUES (1)"))
        for name in (
            "marketing_campaign_v2_campaigns",
            "marketing_campaign_v2_dispatch_approvals",
            "marketing_campaign_v2_governed_executions",
            "marketing_campaign_v2_provider_campaigns",
        ):
            conn.execute(sa.text(f"INSERT INTO {name}(id) VALUES (1), (2), (3), (4)"))


def _insert(conn, *, row_id, approval_id, execution_id, key, status="REVIEW_REQUIRED", pending_digest=None):
    conn.execute(sa.text("""
        INSERT INTO marketing_campaign_v2_background_jobs
        (id, campaign_v2_id, approval_id, execution_id, operator_user_id,
         request_key, manifest_digest, pending_child_ids,
         pending_children_digest, initial_pending_count, start_deadline_at, status)
        VALUES (:id, 1, :approval, :execution, 1,
                :key, :manifest, CAST('[1]' AS json),
                :pending, 1, NOW() + interval '10 minutes', :status)
    """), {
        "id": row_id, "approval": approval_id, "execution": execution_id,
        "key": key * 64, "manifest": "b" * 64,
        "pending": pending_digest or "c" * 64, "status": status,
    })


def test_postgres16_durable_schema_and_no_replay_across_approvals():
    engine = _engine()
    migration = _migration()
    try:
        with engine.connect() as conn:
            assert int(conn.execute(sa.text("SHOW server_version_num")).scalar_one()) >= 160000
        _parents(engine)
        with engine.begin() as conn:
            migration.op = Operations(MigrationContext.configure(conn))
            migration.upgrade()

        inspector = sa.inspect(engine)
        columns = {column["name"] for column in inspector.get_columns(
            "marketing_campaign_v2_background_jobs")}
        assert {"worker_claim_generation", "worker_lease_until", "pending_child_ids"} <= columns
        assert not {"operator_password", "jwt", "phone_number", "api_key"} & columns

        with engine.begin() as conn:
            _insert(conn, row_id=1, approval_id=1, execution_id=1, key="a")

        # A fresh approval/execution cannot bypass an unresolved provider outcome.
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert(conn, row_id=2, approval_id=2, execution_id=2, key="d")

        with engine.begin() as conn:
            rows = conn.execute(sa.text("""
                SELECT id FROM marketing_campaign_v2_background_jobs
                WHERE status='REVIEW_REQUIRED' FOR UPDATE
            """)).all()
            assert [row[0] for row in rows] == [1]

            # Separate connection is not allowed to steal a locked mandate.
            with engine.begin() as other:
                stolen = other.execute(sa.text("""
                    SELECT id FROM marketing_campaign_v2_background_jobs
                    WHERE status='REVIEW_REQUIRED'
                    FOR UPDATE SKIP LOCKED
                """)).all()
                assert stolen == []

        # A verified STOPPED job allows a new approval, not a replay of execution #1.
        with engine.begin() as conn:
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_background_jobs SET status='STOPPED' WHERE id=1
            """))
            _insert(conn, row_id=2, approval_id=2, execution_id=2, key="d")
            count = conn.execute(sa.text("""
                SELECT count(*) FROM marketing_campaign_v2_background_jobs
            """)).scalar_one()
            assert count == 2

        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                _insert(conn, row_id=3, approval_id=3, execution_id=1, key="f")

        # Downgrade must refuse erasing ever-registered jobs, including STOPPED.
        with engine.begin() as conn:
            migration.op = Operations(MigrationContext.configure(conn))
            with pytest.raises(RuntimeError, match="historial"):
                migration.downgrade()
        assert sa.inspect(engine).has_table("marketing_campaign_v2_background_jobs")

        # Exercise the REAL M1c claim code on PostgreSQL, not just raw locks.
        # Patch only identity authorization: the synthetic users stub contains
        # no role columns. HTTP/JWT and role tests run in a separate test file.
        fake_config = {
            "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED": True,
            "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY": True,
            "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED": True,
            "CAMPAIGN_V2_PROVIDER_SEND_ENABLED": True,
        }
        correct_digest = hashlib.sha256(b"[1]").hexdigest()
        with engine.begin() as conn:
            conn.execute(sa.text("""
                UPDATE marketing_campaign_v2_background_jobs
                SET status='STOPPED' WHERE id IN (1, 2)
            """))
            _insert(conn, row_id=3, approval_id=3, execution_id=3, key="e",
                    status="QUEUED", pending_digest=correct_digest)

        with patch.object(worker, "_actor"):
            with Session(engine) as one:
                first = worker.claim_next_queued(
                    session=one, worker_id="synthetic-A", config=fake_config,
                )
            assert first == (3, 1)
            with Session(engine) as two:
                second = worker.claim_next_queued(
                    session=two, worker_id="synthetic-B", config=fake_config,
                )
            assert second is None  # no second claim or HTTP

            # STOP after ownership but BEFORE provider claim: must never call provider.
            with engine.begin() as conn:
                conn.execute(sa.text("""
                    UPDATE marketing_campaign_v2_background_jobs
                    SET status='STOP_REQUESTED' WHERE id=3
                """))
            with Session(engine) as one:
                worker.process_claimed_job(
                    session=one, job_id=3, worker_id="synthetic-A",
                    generation=1, config=fake_config,
                    provider_factory=lambda: (_ for _ in ()).throw(
                        AssertionError("Provider must NOT be called after STOP")),
                )
            with engine.connect() as conn:
                stopped = conn.scalar(sa.text("""
                    SELECT status FROM marketing_campaign_v2_background_jobs WHERE id=3
                """))
                assert stopped == "STOPPED"

            # New work can be claimed, but a crashed RUNNING worker is quarantined,
            # not reacquired by another instance.
            with engine.begin() as conn:
                _insert(conn, row_id=4, approval_id=4, execution_id=4, key="f",
                        status="QUEUED", pending_digest=correct_digest)
            with Session(engine) as one:
                assert worker.claim_next_queued(
                    session=one, worker_id="synthetic-C", config=fake_config,
                ) == (4, 1)
            with engine.begin() as conn:
                conn.execute(sa.text("""
                    UPDATE marketing_campaign_v2_background_jobs
                    SET worker_lease_until = NOW() - interval '1 second' WHERE id=4
                """))
            with Session(engine) as two:
                assert worker.expire_stale_running(session=two) == 1
                assert worker.claim_next_queued(
                    session=two, worker_id="synthetic-D", config=fake_config,
                ) is None
            with engine.connect() as conn:
                state = conn.scalar(sa.text("""
                    SELECT status FROM marketing_campaign_v2_background_jobs WHERE id=4
                """))
                assert state == "REVIEW_REQUIRED"
                count_started = conn.scalar(sa.text("""
                    SELECT count(*) FROM marketing_campaign_v2_background_job_events
                    WHERE job_id=4 AND event_kind='STARTED'
                """))
                assert count_started == 1
    finally:
        engine.dispose()
