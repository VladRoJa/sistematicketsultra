"""Prueba migración usuario 45 en PostgreSQL descartable (no producción)."""
import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions"
    / "b20c10202601_maintenance_lead_regional_scope.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("regional_lead_revision", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _scope(conn, user_id=45):
    return set(conn.execute(sa.text(
        "SELECT sucursal_id FROM usuario_sucursal WHERE user_id=:uid"
    ), {"uid": user_id}).scalars().all())


def test_maintenance_lead_migration_uses_preconditions_and_is_reversible():
    url = os.environ.get("PG_COORD_TEST_URL")
    if not url:
        pytest.skip("Solo PostgreSQL sintético PG_COORD_TEST_URL")
    migration = _migration()
    assert migration.down_revision == "a19c10202601"
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(
                "CREATE TEMP TABLE users (id INTEGER PRIMARY KEY, username TEXT, "
                "rol TEXT, department_id INTEGER, sucursal_id INTEGER)"
            ))
            conn.execute(sa.text(
                "CREATE TEMP TABLE sucursales (sucursal_id INTEGER PRIMARY KEY)"
            ))
            conn.execute(sa.text(
                "CREATE TEMP TABLE usuario_sucursal (user_id INTEGER, sucursal_id INTEGER, "
                "PRIMARY KEY(user_id, sucursal_id))"
            ))
            conn.execute(sa.text(
                "INSERT INTO users VALUES (45,'MANTENIMIENTO','MANTENIMIENTO',1,100),"
                "(91,'MANT_YULIANA','COORDINADOR_MANTENIMIENTO',1,100)"
            ))
            conn.execute(sa.text(
                "INSERT INTO usuario_sucursal VALUES (45,100),(91,9)"
            ))
            for sid in sorted(migration.NEW_BRANCH_IDS | {100}):
                conn.execute(sa.text(
                    "INSERT INTO sucursales VALUES (:sid)"
                ), {"sid": sid})

            migration.op = Operations(MigrationContext.configure(conn))
            # El alcance debe coincidir exactamente con la auditoría de producción.
            conn.execute(sa.text("INSERT INTO usuario_sucursal VALUES (45,9)"))
            with pytest.raises(RuntimeError, match="cambió"):
                migration.upgrade()
            assert _scope(conn) == {9, 100}
            conn.execute(sa.text("DELETE FROM usuario_sucursal WHERE user_id=45 AND sucursal_id=9"))

            migration.upgrade()
            assert _scope(conn) == migration.NEW_BRANCH_IDS
            assert _scope(conn, 91) == {9}
            assert conn.execute(sa.text(
                "SELECT username, rol, department_id, sucursal_id FROM users WHERE id=45"
            )).one() == ("MANTENIMIENTO", "MANTENIMIENTO", 1, 100)
            migration.upgrade()  # idempotencia sin crear duplicados
            assert _scope(conn) == migration.NEW_BRANCH_IDS

            # Impedir rollback silencioso sobre modificaciones posteriores.
            conn.execute(sa.text("INSERT INTO usuario_sucursal VALUES (45,100)"))
            with pytest.raises(RuntimeError, match="Alcance regional"):
                migration.downgrade()
            conn.execute(sa.text("DELETE FROM usuario_sucursal WHERE user_id=45 AND sucursal_id=100"))
            migration.downgrade()
            assert _scope(conn) == {100}
            assert _scope(conn, 91) == {9}
            migration.downgrade()

        with engine.begin() as conn:
            # Tablas temporales desaparecen con la conexión anterior; no hay
            # ningún cambio en estructuras reales de PostgreSQL.
            pass
    finally:
        engine.dispose()


def test_maintenance_lead_migration_skips_database_without_identity():
    url = os.environ.get("PG_COORD_TEST_URL")
    if not url:
        pytest.skip("Solo PostgreSQL sintético PG_COORD_TEST_URL")
    engine = sa.create_engine(url)
    migration = _migration()
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(
                "CREATE TEMP TABLE users (id INTEGER, username TEXT, rol TEXT, "
                "department_id INTEGER, sucursal_id INTEGER)"
            ))
            migration.op = Operations(MigrationContext.configure(conn))
            migration.upgrade()
            migration.downgrade()
    finally:
        engine.dispose()
