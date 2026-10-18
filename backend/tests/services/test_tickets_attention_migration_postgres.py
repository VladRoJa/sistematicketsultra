"""Prueba de la migración V1 en PostgreSQL efímero (nunca producción)."""

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "c17a10202601_tickets_v1_maintenance_attention.py"
)


def test_attention_migration_postgres_upgrade_and_safe_downgrade():
    url = os.environ.get("PG_COORD_TEST_URL")
    if not url:
        pytest.skip("Esta prueba requiere PG_COORD_TEST_URL con DB desechable.")

    engine = sa.create_engine(url)
    spec = importlib.util.spec_from_file_location("tickets_attention_revision", MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    try:
        with engine.begin() as connection:
            connection.execute(sa.text(
                "CREATE TABLE tickets (id INTEGER PRIMARY KEY, asignado_a VARCHAR(50))"
            ))
            connection.execute(sa.text(
                "CREATE TABLE permission_modules ("
                "id INTEGER PRIMARY KEY, key VARCHAR(120) NOT NULL UNIQUE)"
            ))
            connection.execute(sa.text(
                "CREATE TABLE permission_actions ("
                "id SERIAL PRIMARY KEY, module_id INTEGER, key VARCHAR(120), "
                "full_key VARCHAR(240) NOT NULL UNIQUE, name VARCHAR(180), "
                "description TEXT, risk_level VARCHAR(40), is_active BOOLEAN)"
            ))
            connection.execute(sa.text(
                "CREATE TABLE permission_grants (id SERIAL PRIMARY KEY, action_id INTEGER)"
            ))
            connection.execute(sa.text(
                "INSERT INTO permission_modules (id, key) VALUES (1, 'tickets')"
            ))
            connection.execute(sa.text(
                "INSERT INTO tickets (id, asignado_a) VALUES "
                "(10, 'SR_MANT_TIJ'), (11, NULL)"
            ))

            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()

            assigned = connection.execute(sa.text(
                "SELECT tipo_atencion FROM tickets WHERE id = 10"
            )).scalar_one()
            unassigned = connection.execute(sa.text(
                "SELECT tipo_atencion FROM tickets WHERE id = 11"
            )).scalar_one()
            assert assigned == "INTERNA"
            assert unassigned is None

            actions = connection.execute(sa.text(
                "SELECT full_key FROM permission_actions ORDER BY full_key"
            )).scalars().all()
            assert actions == [
                "tickets.maintenance.coordinate",
                "tickets.maintenance.read_assigned_only",
            ]

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(sa.text(
                        "UPDATE tickets SET tipo_atencion='ILEGAL' WHERE id=11"
                    ))

            connection.execute(sa.text(
                "INSERT INTO permission_grants (action_id) "
                "SELECT id FROM permission_actions "
                "WHERE full_key='tickets.maintenance.coordinate'"
            ))
            with pytest.raises(RuntimeError, match="grants"):
                migration.downgrade()

            connection.execute(sa.text("DELETE FROM permission_grants"))
            migration.downgrade()

            remaining_actions = connection.execute(sa.text(
                "SELECT COUNT(*) FROM permission_actions"
            )).scalar_one()
            assert remaining_actions == 0
            remaining_column = connection.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name='tickets' AND column_name='tipo_atencion'"
            )).scalar_one()
            assert remaining_column == 0
    finally:
        engine.dispose()
