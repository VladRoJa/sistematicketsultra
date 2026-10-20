"""Alembic AUTOGESTION en PostgreSQL 16 sintético y descartable."""
import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = (Path(__file__).resolve().parents[2] / "migrations" / "versions"
        / "c21c10202601_yuliana_self_management_attention.py")


def _migration():
    spec = importlib.util.spec_from_file_location("yuliana_autogestion_revision", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_autogestion_constraint_migration_and_safe_downgrade():
    url = os.environ.get("PG_COORD_TEST_URL")
    if not url:
        pytest.skip("Solo corre con PG_COORD_TEST_URL PostgreSQL sintético")
    migration = _migration()
    assert migration.down_revision == "b20c10202601"
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(
                "CREATE TEMP TABLE tickets (id INTEGER PRIMARY KEY, "
                "tipo_atencion VARCHAR(12), CONSTRAINT ck_tickets_tipo_atencion "
                "CHECK (tipo_atencion IS NULL OR tipo_atencion IN ('INTERNA', 'EXTERNA')))"
            ))
            conn.execute(sa.text(
                "INSERT INTO tickets VALUES (1,NULL),(2,'INTERNA'),(3,'EXTERNA')"
            ))
            migration.op = Operations(MigrationContext.configure(conn))
            migration.upgrade()
            conn.execute(sa.text("INSERT INTO tickets VALUES (4,'AUTOGESTION')"))
            assert conn.execute(sa.text(
                "SELECT COUNT(*) FROM tickets WHERE tipo_atencion='AUTOGESTION'"
            )).scalar_one() == 1
            with pytest.raises(RuntimeError, match="seguro revertir"):
                migration.downgrade()
            assert conn.execute(sa.text(
                "SELECT COUNT(*) FROM tickets"
            )).scalar_one() == 4

            conn.execute(sa.text("DELETE FROM tickets WHERE id=4"))
            migration.downgrade()
            assert conn.execute(sa.text(
                "SELECT COUNT(*) FROM tickets WHERE tipo_atencion='INTERNA'"
            )).scalar_one() == 1
            with pytest.raises(sa.exc.IntegrityError):
                with conn.begin_nested():
                    conn.execute(sa.text(
                        "INSERT INTO tickets VALUES (5,'AUTOGESTION')"
                    ))
    finally:
        engine.dispose()
