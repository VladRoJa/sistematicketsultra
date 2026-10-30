"""#1181: prueba aislada de migración de metadato guard sin grants.

SQLite sintético reproduce la identidad de la fila, upgrade, downgrade y
STOP por mapeos alterados. Jamás usa PostgreSQL productivo.
"""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "migrations/versions/p1181c102030_openings_comment_guard_metadata.py"


def _migration():
    spec = importlib.util.spec_from_file_location("permissions_comment_metadata_1181", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(conn, *, action="openings.comment", guard="_require_openings_read"):
    conn.exec_driver_sql(
        """
        CREATE TABLE permission_actions (id INTEGER PRIMARY KEY, full_key TEXT NOT NULL);
        """.strip().rstrip(";")
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE permission_route_map (
            id INTEGER PRIMARY KEY, method TEXT NOT NULL,
            route TEXT NOT NULL, endpoint_function TEXT NOT NULL,
            is_active BOOLEAN NOT NULL, action_id INTEGER,
            current_guard TEXT, current_scope TEXT, review_status TEXT,
            updated_at TEXT
        )
        """.strip()
    )
    conn.execute(
        sa.text("INSERT INTO permission_actions (id, full_key) VALUES (1, :key)"),
        {"key": action},
    )
    conn.execute(
        sa.text("""
            INSERT INTO permission_route_map (
                id, method, route, endpoint_function, is_active,
                action_id, current_guard, current_scope, review_status
            ) VALUES (
                1, 'POST', :route, 'create_task_comment', true,
                1, :guard, 'openings_read_comment_policy', 'needs_manual_decision'
            )
        """),
        {
            "route": "/api/openings/<int:opening_id>/tasks/<int:task_id>/comments",
            "guard": guard,
        },
    )


def _read(conn):
    return conn.execute(
        sa.text("""
            SELECT current_guard, current_scope, review_status
            FROM permission_route_map WHERE id = 1
        """)
    ).one()


def test_migration_preserves_linear_graph_and_prior_head():
    graph = ScriptDirectory(str(ROOT / "migrations"))
    assert len(graph.get_heads()) == 1
    assert graph.get_revision("p1181c102030").down_revision == "n26c10202626"
    assert graph.get_revision("n26c10202626") is not None


def test_upgrade_and_downgrade_change_only_route_metadata():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    migration = _migration()
    with engine.begin() as conn:
        conn.connection.driver_connection.create_function(
            "now", 0, lambda: "2026-10-30T18:00:00Z"
        )
        _seed(conn)
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        assert _read(conn) == (
            "_require_openings_comment",
            "openings_comment_action_independent",
            "guard_separated_flag_off",
        )
        migration.downgrade()
        assert _read(conn) == (
            "_require_openings_read",
            "openings_read_comment_policy",
            "needs_manual_decision",
        )
    engine.dispose()


@pytest.mark.parametrize("action,guard", [
    ("tickets.view", "_require_openings_read"),
    ("openings.comment", "custom_guard_modified_outside_migration"),
])
def test_migration_stops_on_unexpected_catalog_state(action, guard):
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    migration = _migration()
    with engine.begin() as conn:
        _seed(conn, action=action, guard=guard)
        migration.op = Operations(MigrationContext.configure(conn))
        with pytest.raises(RuntimeError):
            migration.upgrade()
        assert _read(conn)[0] == guard
    engine.dispose()
