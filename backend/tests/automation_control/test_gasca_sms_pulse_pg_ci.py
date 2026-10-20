"""Isolated PostgreSQL 15/16 verification for SMS pulse migration and uniqueness."""
import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

from app.extensions import db
from app.models.automation_control import GascaSmsHealthPulseORM as Pulse
from app.services.automation_control.gasca_sms_pulse_service import (
    finish_pulse, pulse_slot_id, read_pulse_health, reserve_pulse,
)


def test_pulse_migration_and_atomic_slot_postgres():
    url = (
        os.getenv("WORKER_HEARTBEAT_TEST_POSTGRES_URL")
        or os.getenv("IVENTAS_DIAG_TEST_POSTGRES_URL")
    )
    if not url:
        pytest.skip("Only runs against explicit ephemeral PostgreSQL test DB")
    path = Path(__file__).resolve().parents[2] / "migrations/versions/f22c10202601_gasca_sms_health_pulses.py"
    spec = importlib.util.spec_from_file_location("pulse_migration_ci", path)
    assert spec is not None and spec.loader is not None
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.revision == "f22c10202601"
    assert mig.down_revision == "d22c10202601"

    engine = sa.create_engine(url)
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    db.init_app(app)
    now = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
    try:
        with engine.begin() as conn:
            assert int(conn.exec_driver_sql("SHOW server_version_num").scalar()) // 10000 in {15, 16}
            mig.op = Operations(MigrationContext.configure(conn))
            mig.upgrade()
            assert "gasca_sms_health_pulses" in sa.inspect(conn).get_table_names()
        with app.app_context():
            slot = reserve_pulse(now)
            assert slot == pulse_slot_id(now)
            assert reserve_pulse(now) is None
            assert db.session.query(Pulse).count() == 1
            finish_pulse(slot, sent=True)
            assert read_pulse_health(now)["state"] == "HEALTHY"
            assert reserve_pulse(now) is None
            db.session.remove()
        with engine.begin() as conn:
            mig.op = Operations(MigrationContext.configure(conn))
            with pytest.raises(RuntimeError, match="historial"):
                mig.downgrade()
            conn.exec_driver_sql("DELETE FROM gasca_sms_health_pulses")
            mig.downgrade()
            assert "gasca_sms_health_pulses" not in sa.inspect(conn).get_table_names()
    finally:
        engine.dispose()
