"""PostgreSQL contract for additive previous-submission exclusion migration."""
from __future__ import annotations

from io import StringIO
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

REVISION = "c29f6a8d1e70"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
URL = os.getenv("PREVIOUS_SUBMIT_TEST_POSTGRES_URL")


def _revision():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)


def test_parent_matches_current_main_head():
    assert _revision().down_revision == "b14d9e2c6f80"


def test_offline_ddl_preserves_existing_frozen_rows(monkeypatch):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision = _revision()
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.upgrade()
    sql = output.getvalue()
    assert "ADD COLUMN related_campaign_id BIGINT" in sql
    assert "PREVIOUS_CAMPAIGN_CONTACT" in sql
    assert "AMBIGUOUS_BRANCH_EVIDENCE" in sql
    assert "FOREIGN KEY(related_campaign_id)" in sql
    assert "ALTER TABLE marketing_campaign_v2_recipients" not in sql
    assert "UPDATE marketing_campaign_v2_recipients" not in sql
    assert "DELETE FROM marketing_campaign_v2_recipients" not in sql


@pytest.mark.skipif(not URL, reason="Needs isolated PostgreSQL CI database")
def test_postgres_existing_exclusions_survive_and_new_reason_is_constrained(monkeypatch):
    url = sa.engine.make_url(URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "previous_submit_ci"
        or url.host not in ("127.0.0.1", "localhost")
        or url.username != "previous_ci"
    ):
        pytest.fail("Refuse non-isolated PostgreSQL URL")

    engine = sa.create_engine(URL, pool_pre_ping=True)
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    campaigns = sa.Table(
        "marketing_campaign_v2_campaigns", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
    )
    recipients = sa.Table(
        "marketing_campaign_v2_recipients", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
    )
    exclusions = sa.Table(
        "marketing_campaign_v2_recipient_dispatch_exclusions", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("campaign_id", sa.BigInteger, sa.ForeignKey(campaigns.c.id), nullable=False),
        sa.Column("recipient_id", sa.BigInteger, sa.ForeignKey(recipients.c.id), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey(users.c.id), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("campaign_id", "recipient_id",
                            name="uq_mkt_v2_recipient_dispatch_exclusions_campaign_recipient"),
        sa.CheckConstraint("reason = 'AMBIGUOUS_BRANCH_EVIDENCE'",
                           name="ck_mkt_v2_recipient_dispatch_exclusion_reason"),
    )

    revision = _revision()
    with engine.begin() as conn:
        metadata.create_all(conn)
        conn.execute(users.insert().values(id=47))
        conn.execute(campaigns.insert(), [{"id": 14}, {"id": 15}])
        conn.execute(recipients.insert(), [{"id": 78091}, {"id": 90001}, {"id": 90002},
                                           {"id": 90003}, {"id": 90004}])
        conn.execute(exclusions.insert().values(
            campaign_id=14, recipient_id=78091, reason="AMBIGUOUS_BRANCH_EVIDENCE",
            created_by_user_id=47,
        ))
        monkeypatch.setattr(
            revision.module, "op", Operations(MigrationContext.configure(conn)),
        )
        revision.module.upgrade()
        table = "marketing_campaign_v2_recipient_dispatch_exclusions"
        assert conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} WHERE reason = 'AMBIGUOUS_BRANCH_EVIDENCE' AND related_campaign_id IS NULL"
        )).scalar_one() == 1

        def insert_exclusion(recipient_id, reason, related):
            conn.execute(sa.text(f"""
                INSERT INTO {table} (
                    campaign_id, recipient_id, reason, related_campaign_id,
                    created_by_user_id
                ) VALUES (15, :recipient, :reason, :related, 47)
            """), {"recipient": recipient_id, "reason": reason, "related": related})

        insert_exclusion(90001, "PREVIOUS_CAMPAIGN_CONTACT", 14)

        for rid, reason, related in [
            (90002, "PREVIOUS_CAMPAIGN_CONTACT", None),
            (90003, "PREVIOUS_CAMPAIGN_CONTACT", 15),
            (90004, "AMBIGUOUS_BRANCH_EVIDENCE", 14),
        ]:
            with conn.begin_nested() as nested:
                with pytest.raises(sa.exc.IntegrityError):
                    insert_exclusion(rid, reason, related)
                nested.rollback()

        with pytest.raises(RuntimeError, match="PREVIOUS_CAMPAIGN_CONTACT"):
            revision.module.downgrade()

        conn.execute(sa.text(
            f"DELETE FROM {table} WHERE reason = 'PREVIOUS_CAMPAIGN_CONTACT'"
        ))
        revision.module.downgrade()
        column_names = {col["name"] for col in sa.inspect(conn).get_columns(table)}
        assert "related_campaign_id" not in column_names
        assert conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one() == 1
        metadata.drop_all(conn)
    engine.dispose()
