"""Issue #856 D3c1 — immutable release-intent schema on isolated PostgreSQL."""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from alembic.operations import Operations

REV = "d856d3c01013"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def test_d3c1_migration_has_linear_parent():
    revision = ScriptDirectory(str(MIGRATIONS)).get_revision(REV)
    assert revision.down_revision == "c856d3b01013"


def test_d3c1_one_intent_per_held_child_and_no_history_downgrade(monkeypatch):
    url = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("isolated PostgreSQL quota_ci required")
    u = sa.engine.make_url(url)
    if (u.get_backend_name() != "postgresql" or u.username != "quota_ci" or
            u.database != "quota_ci" or u.host not in {"localhost", "127.0.0.1"}):
        pytest.fail("Refusing any non-synthetic DB")
    engine = sa.create_engine(url)
    md = sa.MetaData()
    for name, field, ty in [
        ("users","id",sa.Integer),
        ("marketing_campaign_v2_campaigns","id",sa.BigInteger),
        ("marketing_campaign_v2_dispatch_approvals","id",sa.BigInteger),
        ("marketing_campaign_v2_provider_campaigns","id",sa.BigInteger),
    ]:
        sa.Table(name, md, sa.Column(field, ty, primary_key=True))
    revision = ScriptDirectory(str(MIGRATIONS)).get_revision(REV).module
    with engine.begin() as c:
        md.create_all(c)
        monkeypatch.setattr(revision, "op", Operations(MigrationContext.configure(c)))
        revision.upgrade()
        for table, value in [
            ("users",7), ("marketing_campaign_v2_campaigns",77),
            ("marketing_campaign_v2_dispatch_approvals",9),
            ("marketing_campaign_v2_provider_campaigns",100),
        ]:
            c.execute(sa.text(f"INSERT INTO {table} (id) VALUES (:id)"), {"id":value})
        insert = sa.text("""
            INSERT INTO marketing_campaign_v2_held_release_intents
            (source_campaign_id,source_approval_id,source_child_id,
             source_manifest_digest,candidate_fingerprint,candidate_recipients,
             evidence_json,source_reference,reason,requested_by_user_id,
             requested_at,status)
            VALUES (77,9,100,:digest,:candidate,5,'{}'::json,
                    'manual quota evidence','later window',7,now(),
                    'PENDING_FRESH_COHORT')
        """)
        c.execute(insert, {"digest":"a"*64,"candidate":"b"*64})
        with c.begin_nested() as nested:
            with pytest.raises(sa.exc.IntegrityError):
                c.execute(insert, {"digest":"a"*64,"candidate":"b"*64})
            nested.rollback()
        with pytest.raises(RuntimeError, match="historial"):
            revision.downgrade()
        c.execute(sa.text("DELETE FROM marketing_campaign_v2_held_release_intents"))
        revision.downgrade()
        md.drop_all(c)
    engine.dispose()
