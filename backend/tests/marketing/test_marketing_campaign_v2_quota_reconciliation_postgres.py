"""D3b manual reconciliation migration and unique audit on isolated PostgreSQL 16."""
import os
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
REV = "c856d3b01013"


def test_d3b_linear_migration():
    revision = ScriptDirectory(str(MIGRATIONS)).get_revision(REV)
    assert revision.down_revision == "b856d2c01013"


def test_append_only_audit_constraint_postgres(monkeypatch):
    raw = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("synthetic quota_ci PostgreSQL only")
    u = sa.engine.make_url(raw)
    if (u.get_backend_name() != "postgresql" or u.username != "quota_ci" or
            u.database != "quota_ci" or u.host not in {"localhost", "127.0.0.1"}):
        pytest.fail("Refusing any non-synthetic database")
    engine = sa.create_engine(raw)
    md = sa.MetaData()
    for name, column, datatype in [
        ("users", "id", sa.Integer),
        ("marketing_campaign_v2_provider_campaigns", "id", sa.BigInteger),
        ("marketing_campaign_v2_governed_executions", "id", sa.BigInteger),
    ]:
        sa.Table(name, md, sa.Column(column, datatype, primary_key=True))
    mod = ScriptDirectory(str(MIGRATIONS)).get_revision(REV).module
    with engine.begin() as c:
        md.create_all(c)
        monkeypatch.setattr(mod, "op", Operations(MigrationContext.configure(c)))
        mod.upgrade()
        c.execute(sa.text("INSERT INTO users(id) VALUES (7)"))
        c.execute(sa.text("INSERT INTO marketing_campaign_v2_provider_campaigns(id) VALUES (100)"))
        c.execute(sa.text("INSERT INTO marketing_campaign_v2_governed_executions(id) VALUES (41)"))
        sql = sa.text("""
            INSERT INTO marketing_campaign_v2_governed_reconciliation_events
            (execution_id,child_id,event_kind,source_reference,evidence_note,
             previous_child_status,next_child_status,
             previous_execution_status,next_execution_status,
             actor_user_id,recorded_at,evidence_json)
            VALUES(41,100,'STALE_CLAIM_REVIEW','synthetic source','manual verification',
                   'SUBMITTING','RECONCILIATION_REQUIRED',
                   'IN_FLIGHT','REVIEW_REQUIRED',7,now(),'{}'::json)
        """)
        c.execute(sql)
        with c.begin_nested() as sp:
            with pytest.raises(sa.exc.IntegrityError):
                c.execute(sql)
            sp.rollback()
        with pytest.raises(RuntimeError, match="historial"):
            mod.downgrade()
        c.execute(sa.text("DELETE FROM marketing_campaign_v2_governed_reconciliation_events"))
        mod.downgrade()
        md.drop_all(c)
    engine.dispose()
