"""Validate reversible, additive scoped exclusions migration (no frozen updates)."""
from __future__ import annotations

from io import StringIO
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

REVISION = "d8f1c3a9b204"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
URL = os.getenv("M3_TEST_POSTGRES_URL")


def _revision():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)


def test_migration_head_and_parent():
    scripts = ScriptDirectory(str(MIGRATIONS))
    assert scripts.get_heads() == [REVISION]
    assert _revision().down_revision == "f3f1d4e6a7c9"


def test_postgres_ddl_is_additive_and_has_scoped_fk_and_unique(monkeypatch):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision = _revision()
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE marketing_campaign_v2_recipient_dispatch_exclusions" in sql
    assert "UNIQUE (campaign_id, recipient_id)" in sql
    assert "REFERENCES marketing_campaign_v2_recipients (id)" in sql
    assert "REFERENCES users (id)" in sql
    assert "created_by_user_id INTEGER NOT NULL" in sql
    assert "ALTER TABLE marketing_campaign_v2_recipients" not in sql
    assert "UPDATE marketing_campaign_v2_recipients" not in sql
    assert "DELETE FROM marketing_campaign_v2_recipients" not in sql


@pytest.mark.skipif(not URL, reason="Needs dedicated isolated PostgreSQL CI database")
def test_real_postgres_upgrade_constraints_and_downgrade(monkeypatch):
    url = sa.engine.make_url(URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "m3_child_snapshots"
        or url.host not in ("127.0.0.1", "localhost")
        or url.username != "m3_test"
    ):
        pytest.fail("Refuse non-isolated PostgreSQL URL")
    engine = sa.create_engine(URL, pool_pre_ping=True)
    metadata = sa.MetaData()
    actor = sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    campaigns = sa.Table(
        "marketing_campaign_v2_campaigns", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
    )
    recipients = sa.Table(
        "marketing_campaign_v2_recipients", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("campaign_id", sa.BigInteger, nullable=False),
        sa.Column("phone_mx10", sa.String(10), nullable=False),
    )
    revision = _revision()
    with engine.begin() as conn:
        metadata.create_all(conn)
        conn.execute(actor.insert(), [{"id": 42}])
        conn.execute(campaigns.insert(), [{"id": 8}, {"id": 9}])
        conn.execute(recipients.insert(), [
            {"id": rid, "campaign_id": 8, "phone_mx10": f"686{rid:07d}"}
            for rid in (59510, 59859, 60120)
        ])
        before = conn.execute(sa.text("SELECT COUNT(*) FROM marketing_campaign_v2_recipients")).scalar_one()
        assert before == 3
        monkeypatch.setattr(
            revision.module, "op",
            Operations(MigrationContext.configure(conn)),
        )
        revision.module.upgrade()
        table = "marketing_campaign_v2_recipient_dispatch_exclusions"
        for rid in (59510, 59859, 60120):
            conn.execute(sa.text(f"""
                INSERT INTO {table} (
                    campaign_id, recipient_id, reason, created_by_user_id
                ) VALUES (
                    :campaign_id, :recipient_id, 'AMBIGUOUS_BRANCH_EVIDENCE', 42
                )
            """), {"campaign_id": 8, "recipient_id": rid})
        assert conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} WHERE campaign_id = 8"
        )).scalar_one() == 3
        assert conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} WHERE campaign_id = 9"
        )).scalar_one() == 0
        with conn.begin_nested() as nested:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text(f"""
                    INSERT INTO {table} (
                        campaign_id, recipient_id, reason, created_by_user_id
                    ) VALUES (8, 59510, 'AMBIGUOUS_BRANCH_EVIDENCE', 42)
                """))
            nested.rollback()
        assert conn.execute(sa.text("SELECT COUNT(*) FROM marketing_campaign_v2_recipients")).scalar_one() == 3
        revision.module.downgrade()
        assert not sa.inspect(conn).has_table(table)
        assert conn.execute(sa.text("SELECT COUNT(*) FROM marketing_campaign_v2_recipients")).scalar_one() == 3
        metadata.drop_all(conn)
    engine.dispose()
