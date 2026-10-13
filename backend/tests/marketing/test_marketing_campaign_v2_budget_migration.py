"""Alembic real-PostgreSQL regression: cost reference history cannot be lost."""
from __future__ import annotations

from io import StringIO
from pathlib import Path
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

REVISION = "e4b856c9170d"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
POSTGRES = os.getenv("BUDGET_TEST_POSTGRES_URL")


def _module():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION).module


def test_budget_revision_is_linear_successor_of_google_ads_schema():
    revision = ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)
    assert revision.down_revision == "c7e4a9b2d601"


def test_budget_schema_only_and_frozen_campaigns_untouched(monkeypatch):
    output = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    module = _module()
    monkeypatch.setattr(module, "op", Operations(ctx))
    module.upgrade()
    sql = output.getvalue()
    assert "marketing_campaign_v2_cost_rate_revisions" in sql
    assert "NUMERIC(12, 6)" in sql
    assert "unit_cost_mxn > 0" in sql
    assert "marketing_campaign_v2_recipients" not in sql
    assert "UPDATE marketing_campaign_v2_campaigns" not in sql


@pytest.mark.skipif(not POSTGRES, reason="isolated synthetic PostgreSQL DB required")
def test_postgres_budget_constraint_and_fail_closed_downgrade(monkeypatch):
    url = sa.engine.make_url(POSTGRES)
    if (url.get_backend_name() != "postgresql" or url.database != "budget_ci"
        or url.username != "budget_ci" or url.host not in {"127.0.0.1", "localhost"}):
        pytest.fail("Refusing database outside isolated budget_ci")

    engine = sa.create_engine(POSTGRES, pool_pre_ping=True)
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    templates = sa.Table(
        "marketing_campaign_v2_templates", metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
    )
    module = _module()
    with engine.begin() as conn:
        metadata.create_all(conn)
        conn.execute(users.insert().values(id=7))
        conn.execute(templates.insert().values(id=10))
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(conn)))
        module.upgrade()

        conn.execute(sa.text("""
            INSERT INTO marketing_campaign_v2_cost_rate_revisions
                (template_id, provider_channel_id, unit_cost_mxn, valid_from,
                 source_reference, created_by_user_id)
            VALUES (10, 'synthetic-channel', 0.825000, now(), 'CI synthetic', 7)
        """))
        assert conn.execute(sa.text(
            "SELECT COUNT(*) FROM marketing_campaign_v2_cost_rate_revisions"
        )).scalar_one() == 1

        with conn.begin_nested() as savepoint:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(sa.text("""
                    INSERT INTO marketing_campaign_v2_cost_rate_revisions
                        (template_id, provider_channel_id, unit_cost_mxn, valid_from,
                         source_reference, created_by_user_id)
                    VALUES (10, 'negative', -1, now(), 'CI synthetic', 7)
                """))
            savepoint.rollback()

        with pytest.raises(RuntimeError, match="históricas"):
            module.downgrade()
        conn.execute(sa.text("DELETE FROM marketing_campaign_v2_cost_rate_revisions"))
        module.downgrade()
        metadata.drop_all(conn)
    engine.dispose()
