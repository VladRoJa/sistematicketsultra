"""Guard historical Metepec Air Bike recoding on clean PostgreSQL bootstraps."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "a9c4e2f1b7d3_asignar_codigos_air_bike_metepec.py"
)


def _load_migration():
    spec = spec_from_file_location("air_bike_metepec_clean_bootstrap", MIGRATION_PATH)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, value=None, rows=()):
        self.value = value
        self.rows = rows

    def scalar_one(self):
        return self.value

    def fetchall(self):
        return list(self.rows)


class _Connection:
    def __init__(self, *, empty, collisions=()):
        self.empty = empty
        self.collisions = collisions
        self.statements = []
        self.updates = []

    def execute(self, query, params=None):
        sql = str(query)
        self.statements.append(sql)
        if "NOT EXISTS (SELECT 1 FROM inventario_general)" in sql:
            assert "NOT EXISTS (SELECT 1 FROM inventario_sucursal)" in sql
            return _Result(value=self.empty)
        if "SELECT codigo_interno" in sql:
            return _Result(rows=self.collisions)
        if "UPDATE inventario_general" in sql:
            self.updates.append(dict(params))
            return _Result()
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_clean_installation_skips_metepec_data_only_migration(monkeypatch):
    migration = _load_migration()
    connection = _Connection(empty=True)
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(
        migration, "_target_ids",
        lambda bind: pytest.fail("No inventory targets should be queried"),
    )
    migration.upgrade()
    assert len(connection.statements) == 1
    assert connection.updates == []


def test_populated_inventory_with_no_two_targets_still_fails_closed(monkeypatch):
    migration = _load_migration()
    connection = _Connection(empty=False)
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration, "_target_ids", lambda bind: [])
    with pytest.raises(RuntimeError, match="exactamente 2 Air Bike"):
        migration.upgrade()
    assert connection.updates == []


def test_populated_inventory_still_assigns_only_two_expected_codes(monkeypatch):
    migration = _load_migration()
    connection = _Connection(empty=False)
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration, "_target_ids", lambda bind: [101, 102])
    migration.upgrade()
    assert connection.updates == [
        {"inventory_id": 101, "code": "25ABJW202", "equipment_number": "202"},
        {"inventory_id": 102, "code": "25ABJW203", "equipment_number": "203"},
    ]
