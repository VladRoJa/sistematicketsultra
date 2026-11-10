"""Focused SQLite structural contract for BI Vlad branch link migration."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/m1233bimulti111026_ticket_branch_scope.py"
)
spec = importlib.util.spec_from_file_location("bi_vlad_multi_scope", MIGRATION)
assert spec is not None and spec.loader is not None
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def database():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE tickets (id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE sucursales (sucursal_id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO tickets(id) VALUES (9001)"))
        conn.execute(sa.text(
            "INSERT INTO sucursales(sucursal_id) VALUES (4), (5), (21)"
        ))
        ops = Operations(MigrationContext.configure(conn))
        with patch.object(migration, "op", ops):
            yield conn
    engine.dispose()


def test_migration_stores_many_branches_on_one_ticket(database):
    assert migration.down_revision == "m1232bivlad111026"
    migration.upgrade()
    database.execute(sa.text(
        "INSERT INTO ticket_sucursales_alcance(ticket_id, sucursal_id) "
        "VALUES (9001, 4), (9001, 5), (9001, 21)"
    ))
    assert database.execute(sa.text(
        "SELECT COUNT(*) FROM tickets WHERE id = 9001"
    )).scalar_one() == 1
    assert database.execute(sa.text(
        "SELECT COUNT(*) FROM ticket_sucursales_alcance WHERE ticket_id = 9001"
    )).scalar_one() == 3

    with pytest.raises(sa.exc.IntegrityError):
        database.execute(sa.text(
            "INSERT INTO ticket_sucursales_alcance(ticket_id, sucursal_id) "
            "VALUES (9001, 4)"
        ))


def test_downgrade_keeps_operational_scope(database):
    migration.upgrade()
    database.execute(sa.text(
        "INSERT INTO ticket_sucursales_alcance(ticket_id, sucursal_id) "
        "VALUES (9001, 5)"
    ))
    with pytest.raises(RuntimeError, match="tickets operativos"):
        migration.downgrade()
    assert database.execute(sa.text(
        "SELECT COUNT(*) FROM ticket_sucursales_alcance"
    )).scalar_one() == 1


def test_empty_downgrade_removes_only_link_table(database):
    migration.upgrade()
    migration.downgrade()
    assert "ticket_sucursales_alcance" not in sa.inspect(database).get_table_names()
    assert "tickets" in sa.inspect(database).get_table_names()
