from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


REVISION = "c1d5e9a7b204"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def _revision():
    return ScriptDirectory(str(MIGRATIONS)).get_revision(REVISION)


def test_m1_migration_is_single_head_and_extends_current_main_head():
    scripts = ScriptDirectory(str(MIGRATIONS))
    heads = scripts.get_heads()
    assert len(heads) == 1
    lineage = {revision.revision for revision in scripts.iterate_revisions(heads[0], "base")}
    assert REVISION in lineage
    assert _revision().down_revision == "d8f1c3a9b204"


def test_m1_postgres_ddl_contains_domain_constraints(monkeypatch):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision = _revision()
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.upgrade()
    sql = output.getvalue()

    assert "CREATE TABLE system_daily_checks" in sql
    assert "CREATE TABLE system_daily_check_answers" in sql
    assert "CREATE TABLE system_daily_check_issues" in sql
    assert "CREATE TABLE system_daily_check_issue_attachments" in sql
    assert "CREATE TABLE system_daily_check_prompt_states" in sql

    assert "UNIQUE (sucursal_id, business_date)" in sql
    assert "UNIQUE (check_id, question_key)" in sql
    assert "answer IN ('YES', 'NO', 'NA')" in sql
    assert "postpone_count >= 0 AND postpone_count <= 2" in sql
    assert "REFERENCES sucursales (sucursal_id)" in sql
    assert "REFERENCES users (id)" in sql
    assert "REFERENCES system_daily_checks (id)" in sql
    assert "REFERENCES system_daily_check_answers (id)" in sql
    assert "REFERENCES system_daily_check_issues (id)" in sql
    assert "UNIQUE (storage_key)" in sql
    assert "length(sha256) = 64" in sql


def test_m1_postgres_downgrade_drops_all_domain_tables(monkeypatch):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision = _revision()
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.downgrade()
    sql = output.getvalue()

    assert "DROP TABLE system_daily_check_prompt_states" in sql
    assert "DROP TABLE system_daily_check_issue_attachments" in sql
    assert "DROP TABLE system_daily_check_issues" in sql
    assert "DROP TABLE system_daily_check_answers" in sql
    assert "DROP TABLE system_daily_checks" in sql
