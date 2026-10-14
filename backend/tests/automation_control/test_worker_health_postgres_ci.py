"""PostgreSQL 15 heartbeat integration; synthetic, isolated and read-only to vendors."""
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

from app.extensions import db
from app.models.automation_control import SystemWorkerHeartbeatORM
from app.services.automation_control.worker_health_service import (
    emit_worker_heartbeat, read_worker_health,
)


def test_pg15_atomic_upsert_and_revision():
    url = os.getenv("WORKER_HEARTBEAT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires explicit ephemeral PostgreSQL 15 URL")
    path=Path(__file__).resolve().parents[2] / "migrations/versions/c13a70e4d82b_worker_heartbeats.py"
    spec=importlib.util.spec_from_file_location("worker_heartbeat_migration_ci",path)
    assert spec is not None and spec.loader is not None
    mig=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.revision == "c13a70e4d82b"
    assert mig.down_revision == "f62a1b9d4c07"
    engine=sa.create_engine(url)
    app=Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"]=url
    db.init_app(app)
    try:
        with engine.begin() as conn:
            assert int(conn.exec_driver_sql("SHOW server_version_num").scalar()) // 10000 == 15
            mig.op=Operations(MigrationContext.configure(conn))
            mig.upgrade()
        with app.app_context():
            emit_worker_heartbeat("track-scheduler",poll_interval_seconds=60)
            emit_worker_heartbeat("track-scheduler",poll_interval_seconds=75)
            rows=db.session.query(SystemWorkerHeartbeatORM).all()
            assert len(rows)==1
            assert rows[0].poll_interval_seconds==75
            assert rows[0].instance_id and len(rows[0].instance_id)==32
            assert rows[0].last_seen_at is not None
            result=read_worker_health()
            track=next(x for x in result["workers"] if x["worker_key"]=="track-scheduler")
            assert track["status"]=="HEALTHY"
            assert track["instance_count"]==1
            db.session.remove()
        with engine.begin() as conn:
            mig.op=Operations(MigrationContext.configure(conn))
            with pytest.raises(RuntimeError,match="latidos"):
                mig.downgrade()
            conn.exec_driver_sql("DELETE FROM system_worker_heartbeats")
            mig.downgrade()
            assert "system_worker_heartbeats" not in sa.inspect(conn).get_table_names()
    finally:
        engine.dispose()
