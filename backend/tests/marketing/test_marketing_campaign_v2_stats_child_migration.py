"""Offline PostgreSQL DDL checks for Campaign V2 child-stats migration.

This validates migration operations without connecting to production.
A real PostgreSQL upgrade/downgrade is a separate acceptance gate.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
REVISION = "f4a2b6c8d0e1"


def _render(operation_name: str, monkeypatch) -> str:
    revision = ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)
    buffer = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": buffer},
    )
    operations = Operations(context)
    monkeypatch.setattr(revision.module, "op", operations)
    getattr(revision.module, operation_name)()
    return buffer.getvalue()


def test_child_stats_migration_is_linear_head():
    scripts = ScriptDirectory(str(MIGRATIONS))
    assert scripts.get_heads() == [REVISION]
    assert scripts.get_revision(REVISION).down_revision == "f3f1d4e6a7c9"


def test_child_stats_postgresql_upgrade_preserves_legacy_snapshots(monkeypatch):
    sql = _render("upgrade", monkeypatch)
    assert (
        "ALTER TABLE marketing_campaign_v2_provider_stats_snapshots "
        "ADD COLUMN provider_campaign_child_id BIGINT;"
    ) in sql
    assert "NOT NULL" not in sql
    assert "FOREIGN KEY(provider_campaign_child_id)" in sql
    assert "REFERENCES marketing_campaign_v2_provider_campaigns (id)" in sql
    assert "ON DELETE SET NULL" in sql
    assert "CREATE INDEX ix_mkt_v2_stats_provider_campaign_child" in sql
    assert "UPDATE marketing_campaign_v2_provider_stats_snapshots" not in sql
    assert "DELETE FROM marketing_campaign_v2_provider_stats_snapshots" not in sql


def test_child_stats_postgresql_downgrade_is_reversible(monkeypatch):
    sql = _render("downgrade", monkeypatch)
    index = sql.index("DROP INDEX ix_mkt_v2_stats_provider_campaign_child")
    fk = sql.index("DROP CONSTRAINT fk_mkt_v2_stats_provider_campaign_child")
    column = sql.index("DROP COLUMN provider_campaign_child_id")
    assert index < fk < column
