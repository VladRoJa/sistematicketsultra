"""Issue #1129 M3: PostgreSQL 16 schema/claim safety on an EPHEMERAL CI DB.

No real campaigns, no provider calls. Refuses nonlocal/non-synthetic URLs.
This test runs after other PG suites and intentionally keeps its synthetic rows:
GitHub Actions destroys the entire postgres:16 service after the job.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

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
            conn.execute(sa.text(f"INSERT INTO {name}(id) VALUES (1), (2), (3)"))


def _insert(conn, *, row_id, approval_id, execution_id, key, status="REVIEW_REQUIRED"):
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
        "pending": "c" * 64, "status": status,
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
    finally:
        engine.dispose()
