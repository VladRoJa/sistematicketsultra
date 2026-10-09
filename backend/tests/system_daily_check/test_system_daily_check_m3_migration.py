from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


REVISION = "d4a7c91e2b55"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def _revision():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)


def test_m3_rollout_migration_extends_current_main_head():
    scripts = ScriptDirectory(str(MIGRATIONS))
    heads = scripts.get_heads()
    assert len(heads) == 1
    ancestry = {
        revision.revision
        for revision in scripts.iterate_revisions(heads[0], "base")
    }
    assert REVISION in ancestry
    assert _revision().down_revision == "a9d2f6c7b108"


def test_m3_rollout_postgres_ddl_is_auditable(monkeypatch):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision = _revision()
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.upgrade()
    sql = output.getvalue()

    assert "CREATE TABLE system_daily_check_rollout_branches" in sql
    assert "REFERENCES sucursales (sucursal_id)" in sql
    assert "REFERENCES users (id)" in sql
    assert "UNIQUE (sucursal_id, enabled_from)" in sql
    assert (
        "disabled_from IS NULL OR disabled_from >= enabled_from"
        in sql
    )
    assert "ix_system_daily_check_rollout_effective_dates" in sql
    assert "ix_system_daily_check_rollout_branch_dates" in sql


def test_m3_rollout_downgrade_drops_only_rollout_table(monkeypatch):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision = _revision()
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.downgrade()
    sql = output.getvalue()

    assert "DROP TABLE system_daily_check_rollout_branches" in sql
    assert "DROP TABLE system_daily_checks" not in sql
