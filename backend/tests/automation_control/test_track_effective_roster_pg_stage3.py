"""M1-F6/3: enforce future-only immutable attestation at PostgreSQL level."""
import importlib.util
import os
from datetime import timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _revision():
    file = (
        Path(__file__).resolve().parents[2] / "migrations/versions"
        / "f6roster1410b_effective_track_roster_governance.py"
    )
    spec = importlib.util.spec_from_file_location("m1f6_effective_roster_pg", file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _reject(conn, sql, args=None):
    with pytest.raises(sa.exc.DBAPIError):
        with conn.begin_nested():
            conn.execute(sa.text(sql), args or {})


def test_pg15_pg16_attestation_future_only_and_immutable():
    url = os.getenv("TRACK_ROSTER_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires isolated PostgreSQL 15/16 CI database")
    engine = sa.create_engine(url)
    mod = _revision()
    try:
        with engine.begin() as conn:
            assert int(conn.exec_driver_sql("SHOW server_version_num").scalar()) // 10000 in (15, 16)
            conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO users (id) VALUES (8675) ON CONFLICT DO NOTHING")
            mod.op = Operations(MigrationContext.configure(conn))
            mod.upgrade()
            assert not conn.exec_driver_sql(
                "SELECT 1 FROM track_roster_effective_epochs"
            ).fetchall()
            assert not conn.exec_driver_sql(
                "SELECT 1 FROM track_roster_effective_members"
            ).fetchall()
            local_day = conn.exec_driver_sql(
                "SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Tijuana')::DATE"
            ).scalar()
            day = local_day + timedelta(days=2)
            insert = """
                INSERT INTO track_roster_effective_epochs
                    (effective_from, attested_by_user_id,
                     source_reference, expected_branch_count, roster_sha256)
                VALUES (:day, 8675, 'RUNBOOK-TRACK-2026', 2, :hash)
            """
            _reject(conn, insert, {"day": local_day, "hash": "a"*64})
            _reject(conn, insert, {"day": local_day - timedelta(days=2), "hash": "a"*64})
            conn.execute(sa.text(insert), {"day": day, "hash": "a"*64})
            epoch_id = conn.exec_driver_sql(
                "SELECT id FROM track_roster_effective_epochs"
            ).scalar()
            assert epoch_id is not None
            _reject(conn, insert, {"day": local_day + timedelta(days=1), "hash": "a"*64})
            _reject(conn, insert, {"day": day, "hash": "a"*64})
            _reject(conn, """
                UPDATE track_roster_effective_epochs
                SET source_reference='TAMPER-TRACK-001' WHERE id=:id
            """, {"id": epoch_id})
            _reject(conn, """
                UPDATE track_roster_effective_epochs
                SET sealed_at_utc=CURRENT_TIMESTAMP WHERE id=:id
            """, {"id": epoch_id})
            add_member = """
                INSERT INTO track_roster_effective_members
                    (epoch_id, sucursal_canon, sucursal_id_at_attestation)
                VALUES (:id, :code, :source_id)
            """
            conn.execute(sa.text(add_member), {
                "id": epoch_id, "code": "TEC_MXL", "source_id": 7,
            })
            conn.execute(sa.text(add_member), {
                "id": epoch_id, "code": "VILLAS_DEL_REY", "source_id": 8,
            })
            _reject(conn, add_member, {
                "id": epoch_id, "code": "TEC_MXL", "source_id": 7,
            })
            conn.execute(sa.text("""
                UPDATE track_roster_effective_epochs
                SET sealed_at_utc=CURRENT_TIMESTAMP WHERE id=:id
            """), {"id": epoch_id})
            _reject(conn, add_member, {
                "id": epoch_id, "code": "NUEVA", "source_id": 9,
            })
            _reject(conn, """
                UPDATE track_roster_effective_members
                SET sucursal_id_at_attestation=9 WHERE epoch_id=:id
            """, {"id": epoch_id})
            _reject(conn, """
                DELETE FROM track_roster_effective_epochs WHERE id=:id
            """, {"id": epoch_id})
            assert conn.exec_driver_sql(
                "SELECT COUNT(*) FROM track_roster_effective_members"
            ).scalar() == 2
            with pytest.raises(RuntimeError, match="No se elimina"):
                mod.downgrade()
    finally:
        engine.dispose()
