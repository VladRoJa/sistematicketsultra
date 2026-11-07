"""Contract checks for pristine PostgreSQL bootstrap of sucursales."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "422da9dde3bf_backfill_track_branch_catalog_sucursal_.py"
)


def _load_migration():
    spec = spec_from_file_location("branch_catalog_clean_bootstrap_test", MIGRATION_PATH)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


class _CountResult:
    def __init__(self, count):
        self.count = count

    def scalar_one(self):
        return self.count


class _FakeConnection:
    def __init__(self, count):
        self.count = count
        self.insert_payload = None

    def execute(self, statement, payload=None):
        sql = str(statement)
        if sql.strip() == "SELECT COUNT(*) FROM sucursales":
            return _CountResult(self.count)
        assert "INSERT INTO sucursales" in sql
        assert self.insert_payload is None
        self.insert_payload = payload


def test_reference_seed_preserves_historical_identity_before_c9():
    migration = _load_migration()
    rows = migration._CLEAN_BOOTSTRAP_SUCURSALES_PRE_C9
    assert len(rows) == 26
    assert {row[0] for row in rows} == set(range(1, 27))
    by_id = {row[0]: row[2] for row in rows}
    assert by_id[1] == "Villas del rey"
    assert by_id[23] == "Tlalnepantla"
    assert by_id[24] == "Metepec"
    assert by_id[25] == "Saltillo Villalta"
    assert by_id[26] == "Serranía"
    assert "La Viga" not in by_id.values()


def test_pristine_database_gets_only_validated_reference_rows():
    migration = _load_migration()
    conn = _FakeConnection(0)
    migration._seed_sucursales_if_pristine(conn)
    assert len(conn.insert_payload) == 26
    assert {r["sucursal_id"] for r in conn.insert_payload} == set(range(1, 27))
    assert all(
        r["serie"] and r["sucursal"] and r["estado"]
        and r["municipio"] and r["direccion"]
        for r in conn.insert_payload
    )


def test_populated_database_is_not_seeded_or_reconciled():
    migration = _load_migration()
    conn = _FakeConnection(26)
    migration._seed_sucursales_if_pristine(conn)
    assert conn.insert_payload is None
