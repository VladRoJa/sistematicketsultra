"""Real PostgreSQL 16 migration smoke test; isolated random schema."""
import importlib.util
import os
from pathlib import Path
import secrets

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MIGRATION = "a21c10202621"
PARENT = "f22c10202601"


def test_auth_refresh_revision_graph_and_postgres_ddl(monkeypatch):
    url = os.environ.get("AUTH_REFRESH_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("AUTH_REFRESH_TEST_POSTGRES_URL required for PostgreSQL DDL")

    base = Path(__file__).resolve().parents[2]
    alembic_cfg = AlembicConfig()
    alembic_cfg.set_main_option("script_location", str(base / "migrations"))
    script = ScriptDirectory.from_config(alembic_cfg)
    assert script.get_revision(MIGRATION).down_revision == PARENT

    migration_file = (
        base / "migrations" / "versions"
        / "a21c10202621_auth_refresh_sessions.py"
    )
    spec = importlib.util.spec_from_file_location("auth_refresh_migration_ci", migration_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Run DDL in its own unprivileged CI database, with unique schema.
    schema = "auth_refresh_ci_" + secrets.token_hex(5)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
            connection.exec_driver_sql(f"SET search_path TO {schema}")
            connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            monkeypatch.setattr(
                module, "op",
                Operations(MigrationContext.configure(connection)),
            )
            module.upgrade()

            inspector = sa.inspect(connection)
            assert inspector.has_table("auth_refresh_sessions", schema=schema)
            checks = inspector.get_check_constraints(
                "auth_refresh_sessions", schema=schema
            )
            assert any("rotation_count" in c["sqltext"] for c in checks)
            indexes = inspector.get_indexes(
                "auth_refresh_sessions", schema=schema
            )
            assert any(i["name"] == "ix_auth_refresh_sessions_user_id" for i in indexes)

            connection.exec_driver_sql("INSERT INTO users (id) VALUES (47)")
            connection.execute(
                sa.text("""
                    INSERT INTO auth_refresh_sessions
                    (id, user_id, refresh_hash, created_at, last_activity_at,
                     idle_expires_at, absolute_expires_at)
                    VALUES (:sid, 47, :digest, now(), now(),
                            now() + interval '45 minutes',
                            now() + interval '12 hours')
                """),
                {"sid": "a" * 32, "digest": "b" * 64},
            )
            with pytest.raises(RuntimeError, match="No se puede borrar"):
                module.downgrade()

            connection.exec_driver_sql("DELETE FROM auth_refresh_sessions")
            module.downgrade()
            assert not sa.inspect(connection).has_table(
                "auth_refresh_sessions", schema=schema
            )
            connection.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
    finally:
        engine.dispose()
