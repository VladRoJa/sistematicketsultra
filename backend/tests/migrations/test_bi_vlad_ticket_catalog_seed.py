"""Focused synthetic checks for the BI Vlad data migration."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/m1232bivlad111026_ticket_department_catalog.py"
)
spec = importlib.util.spec_from_file_location("bi_vlad_migration", MIGRATION_PATH)
assert spec is not None and spec.loader is not None
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def database():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as bind:
        bind.execute(sa.text("""
            CREATE TABLE departamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(100) NOT NULL
            )
        """))
        bind.execute(sa.text("""
            CREATE TABLE catalogo_clasificacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(100) NOT NULL,
                parent_id INTEGER NULL,
                departamento_id INTEGER NOT NULL,
                nivel INTEGER NOT NULL,
                activo BOOLEAN NOT NULL DEFAULT 1
            )
        """))
        yield bind
    engine.dispose()


def _run_upgrade(bind):
    with patch.object(migration.op, "get_bind", return_value=bind):
        migration.upgrade()


def test_seed_creates_root_and_four_categories_idempotently(database):
    database.execute(sa.text("INSERT INTO departamentos(nombre) VALUES ('Sistemas')"))
    _run_upgrade(database)
    _run_upgrade(database)

    rows = database.execute(sa.text("""
        SELECT c.nombre, c.nivel, c.parent_id, c.activo, c.departamento_id
        FROM catalogo_clasificacion c
        ORDER BY c.nivel, c.nombre
    """)).mappings().all()
    assert len(rows) == 5
    root = rows[0]
    assert root["nombre"] == "BI Vlad"
    assert root["nivel"] == 1
    assert root["parent_id"] is None
    assert root["activo"] == 1
    root_id = database.execute(sa.text("""
        SELECT id FROM catalogo_clasificacion WHERE parent_id IS NULL
    """)).scalar_one()
    assert {row["nombre"] for row in rows[1:]} == set(migration.CATEGORY_NAMES)
    assert all(row["parent_id"] == root_id for row in rows[1:])
    assert all(row["departamento_id"] == root["departamento_id"] for row in rows)
    assert database.execute(sa.text("SELECT COUNT(*) FROM departamentos")).scalar_one() == 2


def test_seed_reuses_existing_department_and_refuses_duplicate_root(database):
    database.execute(sa.text("INSERT INTO departamentos(nombre) VALUES ('BI Vlad')"))
    _run_upgrade(database)
    assert database.execute(sa.text("SELECT COUNT(*) FROM departamentos")).scalar_one() == 1

    root_id = database.execute(sa.text("""
        SELECT id FROM catalogo_clasificacion WHERE parent_id IS NULL
    """)).scalar_one()
    database.execute(sa.text("""
        INSERT INTO catalogo_clasificacion(nombre, parent_id, departamento_id, nivel, activo)
        SELECT 'BI Vlad', NULL, departamento_id, 1, 1
        FROM catalogo_clasificacion WHERE id = :id
    """), {"id": root_id})
    with pytest.raises(RuntimeError, match="duplicada"):
        _run_upgrade(database)


def test_downgrade_does_not_delete_operational_catalog(database):
    _run_upgrade(database)
    with pytest.raises(RuntimeError, match="reversión automática bloqueada"):
        migration.downgrade()
    assert database.execute(sa.text("SELECT COUNT(*) FROM catalogo_clasificacion")).scalar_one() == 5
