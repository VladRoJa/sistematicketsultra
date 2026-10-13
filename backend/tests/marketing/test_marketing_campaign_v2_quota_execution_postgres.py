"""D2c execution authorization Alembic schema, isolated PostgreSQL 16 only."""
from io import StringIO
from pathlib import Path
import os

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
REV = "b856d2c01013"


def migration():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REV)


def test_migration_is_linear_and_schema_only(monkeypatch):
    r = migration()
    assert r.down_revision == "a856d2a01013"
    out = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": out},
    )
    monkeypatch.setattr(r.module, "op", Operations(ctx))
    r.module.upgrade()
    sql = out.getvalue()
    assert "marketing_campaign_v2_governed_executions" in sql
    assert "uq_mkt_v2_governed_execution_approval" in sql
    assert "IN_FLIGHT" in sql
    assert "UPDATE marketing_campaign" not in sql


def test_governed_execution_constraints_real_postgres(monkeypatch):
    raw = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("isolated quota_ci required")
    uri = sa.engine.make_url(raw)
    if (uri.get_backend_name() != "postgresql" or
            uri.username != "quota_ci" or uri.database != "quota_ci" or
            uri.host not in {"127.0.0.1", "localhost"}):
        pytest.fail("Refusing database other than synthetic quota_ci")
    engine = sa.create_engine(raw)
    md = sa.MetaData()
    sa.Table("users", md, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("marketing_campaign_v2_dispatch_approvals", md,
             sa.Column("id", sa.BigInteger, primary_key=True))
    sa.Table("marketing_campaign_v2_provider_campaigns", md,
             sa.Column("id", sa.BigInteger, primary_key=True))
    r = migration().module
    with engine.begin() as c:
        md.create_all(c)
        monkeypatch.setattr(r, "op", Operations(MigrationContext.configure(c)))
        r.upgrade()
        c.execute(sa.text("INSERT INTO users (id) VALUES (7)"))
        c.execute(sa.text("INSERT INTO marketing_campaign_v2_dispatch_approvals (id) VALUES (9)"))
        c.execute(sa.text("""
            INSERT INTO marketing_campaign_v2_governed_executions
            (approval_id,manifest_digest,confirmed_by_user_id,
             confirmed_at,expires_at,status)
            VALUES (9,:digest,7,now(),now()+interval '10 minutes','AUTHORIZED')
        """), {"digest": "a" * 64})
        with c.begin_nested() as sp:
            with pytest.raises(sa.exc.IntegrityError):
                c.execute(sa.text("""
                    INSERT INTO marketing_campaign_v2_governed_executions
                    (approval_id,manifest_digest,confirmed_by_user_id,
                     confirmed_at,expires_at,status)
                    VALUES (9,:digest,7,now(),now()+interval '10 minutes','AUTHORIZED')
                """), {"digest": "b" * 64})
            sp.rollback()
        with pytest.raises(RuntimeError, match="historial"):
            r.downgrade()
        c.execute(sa.text("DELETE FROM marketing_campaign_v2_governed_executions"))
        r.downgrade()
        md.drop_all(c)
    engine.dispose()
