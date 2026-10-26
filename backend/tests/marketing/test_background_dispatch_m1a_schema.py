"""Issue #1129 M1a: schema, idempotency and no destructive rollback.

SQLite tests are contract smoke checks. Real PostgreSQL 16 is a separate gate
and is NEVER pointed at the production database.
"""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "migrations/versions/n26c10202626_campaign_v2_background_jobs.py"


def _migration():
    spec = importlib.util.spec_from_file_location("issue1129_m1a", FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def schema():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    migration = _migration()
    with engine.begin() as conn:
        stub = sa.MetaData()
        sa.Table("users", stub, sa.Column("id", sa.Integer, primary_key=True))
        for name in (
            "marketing_campaign_v2_campaigns",
            "marketing_campaign_v2_dispatch_approvals",
            "marketing_campaign_v2_governed_executions",
            "marketing_campaign_v2_provider_campaigns",
        ):
            sa.Table(name, stub, sa.Column("id", sa.BigInteger, primary_key=True))
        stub.create_all(conn)
        conn.execute(sa.text("INSERT INTO users(id) VALUES (1)"))
        for name in (
            "marketing_campaign_v2_campaigns",
            "marketing_campaign_v2_dispatch_approvals",
            "marketing_campaign_v2_governed_executions",
            "marketing_campaign_v2_provider_campaigns",
        ):
            conn.execute(sa.text(f"INSERT INTO {name}(id) VALUES (1), (2)"))
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
    yield engine, migration
    engine.dispose()


def _insert(conn, **overrides):
    from datetime import datetime, timezone, timedelta
    row = dict(
        id=1, campaign_v2_id=1, approval_id=1, execution_id=1,
        operator_user_id=1, request_key="a" * 64, manifest_digest="b" * 64,
        pending_children_digest="c" * 64, pending_child_ids="[1]",
        initial_pending_count=1, start_deadline_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join(":" + key for key in row)
    conn.execute(sa.text(
        f"INSERT INTO marketing_campaign_v2_background_jobs({columns}) VALUES({placeholders})"), row)


def test_revision_is_linear():
    migration = _migration()
    assert migration.revision == "n26c10202626"
    assert migration.down_revision == "m23c10202623"


def test_schema_has_no_secrets(schema):
    engine, _ = schema
    inspect = sa.inspect(engine)
    cols = {c["name"] for c in inspect.get_columns("marketing_campaign_v2_background_jobs")}
    assert {"execution_id", "operator_user_id", "pending_children_digest",
            "worker_claim_generation", "worker_lease_until"} <= cols
    assert not {"operator_password", "jwt", "api_key", "recipient_phone"} & cols
    assert inspect.has_table("marketing_campaign_v2_background_job_events")


def test_unique_execution_and_review_blocks_new_job(schema):
    engine, _ = schema
    with engine.begin() as conn:
        _insert(conn, status="REVIEW_REQUIRED")
    with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            _insert(conn, id=2, execution_id=2, approval_id=2, request_key="d" * 64)
        conn.rollback()
        with pytest.raises(IntegrityError):
            _insert(conn, id=2, execution_id=1, approval_id=2, request_key="d" * 64)
        conn.rollback()


@pytest.mark.parametrize("invalid", [
    {"status": "AUTO_RETRY"}, {"initial_pending_count": 0},
    {"worker_claim_generation": -1}, {"manifest_digest": "short"},
])
def test_invalid_rows_rejected(schema, invalid):
    engine, _ = schema
    with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            _insert(conn, **invalid)
        conn.rollback()


def test_downgrade_refuses_history(schema):
    engine, migration = schema
    with engine.begin() as conn:
        _insert(conn)
    with engine.connect() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        with pytest.raises(RuntimeError, match="historial"):
            migration.downgrade()
        conn.rollback()
        assert sa.inspect(conn).has_table("marketing_campaign_v2_background_jobs")


def test_empty_downgrade(schema):
    engine, migration = schema
    with engine.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.downgrade()
    assert not sa.inspect(engine).has_table("marketing_campaign_v2_background_jobs")


def test_postgres16_gate_requires_disposable_database():
    import os
    url = os.getenv("CAMPAIGN_V2_BG_M1A_TEST_PG_URL")
    if not url:
        pytest.skip("PostgreSQL 16 QA pendiente: base sintética no disponible")
    u = sa.engine.make_url(url)
    # Refuse accidental production connections even when a URL is supplied.
    assert u.get_backend_name() == "postgresql"
    assert u.host in {"localhost", "127.0.0.1"}
    assert u.database == "quota_ci" and u.username == "quota_ci"
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            assert int(conn.execute(sa.text("SHOW server_version_num")).scalar_one()) >= 160000
    finally:
        engine.dispose()
