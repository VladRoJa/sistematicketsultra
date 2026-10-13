"""D3c2 Alembic: frozen campaign linkage cannot be reused, history preserved."""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def test_revision_is_linear():
    revision = ScriptDirectory(str(MIGRATIONS)).get_revision("e856d3c21013")
    assert revision.down_revision == "d856d3c01013"


def test_freeze_link_is_unique_and_downgrade_protected(monkeypatch):
    url = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("isolated PostgreSQL quota_ci only")
    parts = sa.engine.make_url(url)
    if (parts.get_backend_name() != "postgresql" or parts.database != "quota_ci" or
            parts.username != "quota_ci" or
            parts.host not in {"127.0.0.1", "localhost"}):
        pytest.fail("Refusing non-synthetic DB")

    md = sa.MetaData()
    for name, field, ty in [
        ("users","id",sa.Integer),
        ("marketing_campaign_v2_campaigns","id",sa.BigInteger),
        ("marketing_campaign_v2_dispatch_approvals","id",sa.BigInteger),
        ("marketing_campaign_v2_provider_campaigns","id",sa.BigInteger),
    ]:
        sa.Table(name, md, sa.Column(field, ty, primary_key=True))
    script = ScriptDirectory(str(MIGRATIONS))
    d3c1 = script.get_revision("d856d3c01013").module
    d3c2 = script.get_revision("e856d3c21013").module
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        md.create_all(conn)
        for mod in (d3c1,d3c2):
            monkeypatch.setattr(mod, "op", Operations(MigrationContext.configure(conn)))
            mod.upgrade()
        conn.execute(sa.text("INSERT INTO users(id) VALUES (7)"))
        conn.execute(sa.text("INSERT INTO marketing_campaign_v2_campaigns(id) VALUES (77),(999)"))
        conn.execute(sa.text("INSERT INTO marketing_campaign_v2_dispatch_approvals(id) VALUES (9)"))
        conn.execute(sa.text("INSERT INTO marketing_campaign_v2_provider_campaigns(id) VALUES (100)"))
        conn.execute(sa.text("""
            INSERT INTO marketing_campaign_v2_held_release_intents
            (source_campaign_id,source_approval_id,source_child_id,
             source_manifest_digest,candidate_fingerprint,candidate_recipients,
             evidence_json,source_reference,reason,requested_by_user_id,
             requested_at,status)
            VALUES (77,9,100,:digest,:candidate,5,'{}'::json,'source','reason',7,now(),
                    'PENDING_FRESH_COHORT')
        """), {"digest":"a"*64,"candidate":"b"*64})
        with conn.begin_nested() as nested:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text("""
                    UPDATE marketing_campaign_v2_held_release_intents
                    SET status='FROZEN_DERIVED' WHERE source_child_id=100
                """))
            nested.rollback()
        conn.execute(sa.text("""
            UPDATE marketing_campaign_v2_held_release_intents
            SET status='FROZEN_DERIVED',derived_campaign_id=999,materialized_at=now()
            WHERE source_child_id=100
        """))
        with pytest.raises(RuntimeError, match="perder"):
            d3c2.downgrade()
        conn.execute(sa.text("""
            UPDATE marketing_campaign_v2_held_release_intents
            SET status='PENDING_FRESH_COHORT',derived_campaign_id=NULL,materialized_at=NULL
            WHERE source_child_id=100
        """))
        d3c2.downgrade()
        conn.execute(sa.text("DELETE FROM marketing_campaign_v2_held_release_intents"))
        d3c1.downgrade()
        md.drop_all(conn)
    engine.dispose()
