"""Migración de Yuliana, en base PostgreSQL descartable: nunca producción."""

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "a19c10202601_yuliana_maintenance_coordinator.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location(
        "yuliana_coordinator_revision", MIGRATION_PATH,
    )
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


def _seed(connection, migration):
    # Tablas temporales para aislar el test de otros jobs en PostgreSQL.
    statements = (
        "CREATE TEMP TABLE users (id INTEGER PRIMARY KEY, username TEXT, "
        "rol TEXT, department_id INTEGER)",
        "CREATE TEMP TABLE usuarios_permisos "
        "(user_id INTEGER, departamento_id INTEGER, es_admin BOOLEAN)",
        "CREATE TEMP TABLE usuario_sucursal (user_id INTEGER, sucursal_id INTEGER)",
        "CREATE TEMP TABLE permission_actions "
        "(id INTEGER, full_key TEXT, is_active BOOLEAN)",
        "CREATE TEMP TABLE permission_grants "
        "(principal_type TEXT, principal_user_id INTEGER, action_id INTEGER, "
        "scope_type TEXT, is_active BOOLEAN, deleted_at TIMESTAMPTZ, "
        "starts_at TIMESTAMPTZ, expires_at TIMESTAMPTZ, effect TEXT)",
    )
    for statement in statements:
        connection.execute(sa.text(statement))

    connection.execute(sa.text(
        "INSERT INTO users (id, username, rol, department_id) "
        "VALUES (91, 'COMPRAS_YULIANA', 'COMPRAS', 6)"
    ))
    connection.execute(sa.text(
        "INSERT INTO usuarios_permisos VALUES (91, 1, FALSE)"
    ))
    connection.execute(sa.text(
        "INSERT INTO permission_actions "
        "VALUES (1, 'tickets.maintenance.coordinate', TRUE)"
    ))
    connection.execute(sa.text(
        "INSERT INTO permission_grants "
        "(principal_type, principal_user_id, action_id, scope_type, "
        "is_active, effect) VALUES ('user', 91, 1, 'global', TRUE, 'allow')"
    ))
    for branch_id in migration.EXPECTED_BRANCHES:
        connection.execute(sa.text(
            "INSERT INTO usuario_sucursal VALUES (91, :branch_id)"
        ), {"branch_id": branch_id})


def _identity(connection):
    return connection.execute(sa.text(
        "SELECT username, rol, department_id FROM users WHERE id = 91"
    )).one()


def test_yuliana_migration_requires_exact_grants_and_preserves_history():
    url = os.environ.get("PG_COORD_TEST_URL")
    if not url:
        pytest.skip("Solo corre en PostgreSQL desechable PG_COORD_TEST_URL.")

    migration = _migration()
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            _seed(connection, migration)
            migration.op = Operations(MigrationContext.configure(connection))

            # Sin grants vigentes no modifica la identidad.
            connection.execute(sa.text("UPDATE permission_grants SET effect='deny'"))
            with pytest.raises(RuntimeError, match="coordinación"):
                migration.upgrade()
            assert _identity(connection) == ("COMPRAS_YULIANA", "COMPRAS", 6)
            connection.execute(sa.text("UPDATE permission_grants SET effect='allow'"))

            # Si la región cambia, fallar cerrado.
            connection.execute(sa.text(
                "INSERT INTO usuario_sucursal VALUES (91, 1000)"
            ))
            with pytest.raises(RuntimeError, match="alcance regional"):
                migration.upgrade()
            connection.execute(sa.text(
                "DELETE FROM usuario_sucursal WHERE sucursal_id=1000"
            ))

            migration.upgrade()
            assert _identity(connection) == (
                "MANT_YULIANA", "COORDINADOR_MANTENIMIENTO", 1,
            )
            assert connection.execute(sa.text(
                "SELECT COUNT(*) FROM usuarios_permisos WHERE user_id=91"
            )).scalar_one() == 1
            assert connection.execute(sa.text(
                "SELECT COUNT(*) FROM usuario_sucursal WHERE user_id=91"
            )).scalar_one() == len(migration.EXPECTED_BRANCHES)

            # Repetible y reversible para el usuario, sin alterar trazas.
            migration.upgrade()
            assert _identity(connection)[0] == "MANT_YULIANA"
            migration.downgrade()
            assert _identity(connection) == ("COMPRAS_YULIANA", "COMPRAS", 6)
    finally:
        engine.dispose()
