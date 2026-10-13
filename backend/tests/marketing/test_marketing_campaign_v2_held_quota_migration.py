"""Migration and database constraints for durable held quota batches."""
from __future__ import annotations

from io import StringIO
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

REVISION = "d92c15a8f63b"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
URL = os.getenv("HELD_QUOTA_TEST_POSTGRES_URL")


def _revision():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)


def test_migration_parent_is_previous_campaign_contact_revision():
    assert _revision().down_revision == "c29f6a8d1e70"


def test_offline_postgres_ddl_never_modifies_frozen_recipient_table(monkeypatch):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision = _revision()
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.upgrade()
    sql = output.getvalue()
    assert "ADD COLUMN hold_reason" in sql
    assert "ADD COLUMN held_by_user_id" in sql
    assert "ADD COLUMN held_at" in sql
    assert "ADD COLUMN hold_evidence_json" in sql
    assert "HELD" in sql
    assert "CHANNEL_DAILY_QUOTA" in sql
    assert "ALTER TABLE marketing_campaign_v2_recipients" not in sql
    assert "UPDATE marketing_campaign_v2_recipients" not in sql
    assert "DELETE FROM marketing_campaign_v2_recipients" not in sql


@pytest.mark.skipif(not URL, reason="Requires isolated HELD quota PostgreSQL CI DB")
def test_postgres_upgrade_and_held_audit_constraints(monkeypatch):
    url = sa.engine.make_url(URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "held_quota_ci"
        or url.username != "hold_ci"
        or url.host not in {"127.0.0.1", "localhost"}
    ):
        pytest.fail("Refuse non-isolated PostgreSQL URL")

    engine = sa.create_engine(URL, pool_pre_ping=True)
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    provider = sa.Table(
        "marketing_campaign_v2_provider_campaigns",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provider_campaign_id", sa.String(255), nullable=True),
        sa.Column("submit_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PREPARED','READY','BLOCKED','SUBMITTING',"
            "'SUBMITTED','SCHEDULED','RETRY_ELIGIBLE','RETRY_EXHAUSTED',"
            "'PROVIDER_ERROR','RECONCILIATION_REQUIRED')",
            name="ck_marketing_campaign_v2_provider_campaign_status",
        ),
    )
    revision = _revision()
    with engine.begin() as conn:
        metadata.create_all(conn)
        conn.execute(users.insert(), [{"id": 7}])
        conn.execute(provider.insert(), [
            {"id": 1, "status": "READY"},
            {"id": 2, "status": "SUBMITTED", "provider_campaign_id": "provider-existing"},
        ])
        monkeypatch.setattr(
            revision.module, "op",
            Operations(MigrationContext.configure(conn)),
        )
        revision.module.upgrade()
        table = "marketing_campaign_v2_provider_campaigns"

        # Existing READY/SUBMITTED records remain untouched.
        assert conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} WHERE status IN ('READY','SUBMITTED')"
        )).scalar_one() == 2

        def add_held(*, id, reason="CHANNEL_DAILY_QUOTA", actor=7, started=None):
            conn.execute(sa.text(f"""
                INSERT INTO {table}
                    (id, status, hold_reason, held_by_user_id, held_at, submit_started_at)
                VALUES (:id, 'HELD', :reason, :actor, now(), :started)
            """), {"id": id, "reason": reason, "actor": actor, "started": started})

        add_held(id=3)
        assert conn.execute(sa.text(
            f"SELECT hold_reason FROM {table} WHERE id = 3"
        )).scalar_one() == "CHANNEL_DAILY_QUOTA"

        for data in [
            {"id": 4, "reason": None},
            {"id": 5, "actor": None},
            {"id": 6, "reason": "OTHER_REASON"},
            {"id": 7, "started": sa.text("now()")},
        ]:
            # Last case is exercised with direct SQL below rather than binding a SQL expression.
            if data["id"] == 7:
                continue
            with conn.begin_nested() as nested:
                with pytest.raises(sa.exc.IntegrityError):
                    add_held(**data)
                nested.rollback()

        with conn.begin_nested() as nested:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text(
                    f"UPDATE {table} SET submit_started_at = now() WHERE id = 3"
                ))
            nested.rollback()

        with pytest.raises(RuntimeError, match="retencion"):
            revision.module.downgrade()

        conn.execute(sa.text(f"DELETE FROM {table} WHERE id = 3"))
        revision.module.downgrade()

        assert "hold_reason" not in {
            col["name"] for col in sa.inspect(conn).get_columns(table)
        }
        assert conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 2
        metadata.drop_all(conn)
    engine.dispose()
