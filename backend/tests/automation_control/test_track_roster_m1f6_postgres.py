"""M1-F6 stage-1: PostgreSQL 15/16 roster evidence gates, no real data."""
import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.warehouse import (
    TrackVersionRosterSnapshotORM, TrackVersionRosterMemberORM,
)


def _revision():
    file = (Path(__file__).resolve().parents[2] / "migrations/versions"
            / "f6roster1014_track_version_roster_evidence.py")
    spec = importlib.util.spec_from_file_location("m1f6_roster_schema", file)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stage_1_contract_no_auto_legacy_certification():
    mod = _revision()
    assert mod.revision == "f6roster1014"
    assert mod.down_revision == "c856map1014"
    assert TrackVersionRosterSnapshotORM.__tablename__ == mod.SNAPSHOT
    assert TrackVersionRosterMemberORM.__tablename__ == mod.MEMBER
    assert TrackVersionRosterSnapshotORM.__table__.primary_key.columns.keys() == ["version_id"]
    assert TrackVersionRosterMemberORM.__table__.primary_key.columns.keys() == [
        "version_id", "sucursal_canon",
    ]
    assert "historical_roster_verified" in TrackVersionRosterSnapshotORM.__table__.columns


def _reject(conn, sql, params=None):
    """Savepoint so an expected PostgreSQL constraint failure cannot abort the test."""
    with pytest.raises(sa.exc.DBAPIError):
        with conn.begin_nested():
            conn.execute(sa.text(sql), params or {})


def test_pg_roster_capture_sealing_and_no_retrospective_claims():
    url = os.getenv("TRACK_ROSTER_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires explicit isolated PostgreSQL 15/16 URL")
    engine = sa.create_engine(url)
    mod = _revision()
    try:
        with engine.begin() as conn:
            major = int(conn.exec_driver_sql("SHOW server_version_num").scalar()) // 10000
            assert major in (15, 16)
            # Synthetic parent: no access to actual production Track versions.
            conn.exec_driver_sql("""
                CREATE TABLE track_daily_versions (
                    id BIGINT PRIMARY KEY,
                    track_date DATE NOT NULL,
                    status TEXT NOT NULL,
                    started_at_utc TIMESTAMPTZ
                )
            """)
            conn.exec_driver_sql("""
                INSERT INTO track_daily_versions VALUES
                (501, DATE '2026-10-14', 'running', CURRENT_TIMESTAMP),
                (502, DATE '2026-10-13', 'success', CURRENT_TIMESTAMP),
                (503, DATE '2026-10-14', 'running', CURRENT_TIMESTAMP)
            """)
            mod.op = Operations(MigrationContext.configure(conn))
            mod.upgrade()
            assert mod.SNAPSHOT in sa.inspect(conn).get_table_names()
            assert mod.MEMBER in sa.inspect(conn).get_table_names()
            assert conn.exec_driver_sql(
                "SELECT count(*) FROM track_version_roster_snapshots"
            ).scalar() == 0

            insert_header = """
                INSERT INTO track_version_roster_snapshots
                 (version_id, track_date, expected_branch_count, roster_sha256)
                VALUES (:v, :d, :n, :digest)
            """
            _reject(conn, insert_header, {
                "v": 502, "d": "2026-10-13", "n": 26, "digest": "a"*64,
            })
            _reject(conn, insert_header, {
                "v": 501, "d": "2026-10-13", "n": 2, "digest": "a"*64,
            })
            _reject(conn, insert_header, {
                "v": 501, "d": "2026-10-14", "n": 2, "digest": "not-a-digest",
            })
            conn.execute(sa.text(insert_header), {
                "v": 501, "d": "2026-10-14", "n": 2, "digest": "a"*64,
            })
            _reject(conn, insert_header, {
                "v": 501, "d": "2026-10-14", "n": 2, "digest": "a"*64,
            })
            _reject(conn, """
                UPDATE track_version_roster_snapshots
                SET historical_roster_verified=TRUE WHERE version_id=501
            """)
            _reject(conn, """
                UPDATE track_version_roster_snapshots
                SET sealed_at_utc=CURRENT_TIMESTAMP WHERE version_id=501
            """)
            members = sa.text("""
                INSERT INTO track_version_roster_members
                (version_id, sucursal_canon, sucursal_id_at_capture)
                VALUES (501, :code, :branch_id)
            """)
            conn.execute(members, {"code": "TEC_MXL", "branch_id": 7})
            conn.execute(members, {"code": "VILLAS_DEL_REY", "branch_id": 8})
            _reject(conn, str(members), {"code": "TEC_MXL", "branch_id": 7})
            conn.exec_driver_sql("""
                UPDATE track_version_roster_snapshots
                SET sealed_at_utc=CURRENT_TIMESTAMP WHERE version_id=501
            """)
            _reject(conn, str(members), {"code": "OTRA", "branch_id": 9})
            _reject(conn, """
                UPDATE track_version_roster_members SET sucursal_canon='OTRA'
                WHERE version_id=501 AND sucursal_canon='TEC_MXL'
            """)
            _reject(conn, """
                DELETE FROM track_version_roster_members WHERE version_id=501
            """)
            _reject(conn, """
                UPDATE track_version_roster_snapshots
                SET expected_branch_count=3 WHERE version_id=501
            """)
            _reject(conn, """
                DELETE FROM track_version_roster_snapshots WHERE version_id=501
            """)
            assert conn.exec_driver_sql("""
                SELECT expected_branch_count, historical_roster_verified,
                       sealed_at_utc IS NOT NULL
                FROM track_version_roster_snapshots WHERE version_id=501
            """).one() == (2, False, True)
            assert conn.exec_driver_sql(
                "SELECT count(*) FROM track_version_roster_members WHERE version_id=501"
            ).scalar() == 2

            with pytest.raises(RuntimeError, match="No se elimina evidencia"):
                mod.downgrade()
    finally:
        engine.dispose()
