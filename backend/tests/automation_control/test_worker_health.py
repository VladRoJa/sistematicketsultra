"""Worker liveness is distinct from job results; auth and no false green."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.extensions import db
from app.models.automation_control import SystemWorkerHeartbeatORM as Heartbeat
from app.routes.automation_control_routes import automation_control_bp
from app.services.automation_control.worker_health_service import (
    emit_worker_heartbeat, read_worker_health,
)


@pytest.fixture
def health_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        JWT_SECRET_KEY="heartbeat-test-only",
    )
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(automation_control_bp, url_prefix="/api/automation-control")
    with app.app_context():
        Heartbeat.__table__.create(db.engine)
        yield app
        db.session.remove()


def _beat(key, instance, seen, *, enabled=True, poll=60):
    return Heartbeat(
        worker_key=key, instance_id=instance,
        started_at=seen-timedelta(hours=1), last_seen_at=seen,
        poll_interval_seconds=poll, enabled=enabled,
    )


def _status(payload, key="track-scheduler"):
    return next(x for x in payload["workers"] if x["worker_key"] == key)


def test_unknown_without_heartbeats_never_green(health_app):
    result=read_worker_health(datetime(2026,10,14,18,tzinfo=timezone.utc))
    assert len(result["workers"]) == 5
    assert all(x["status"] == "UNKNOWN" for x in result["workers"])
    assert all(x["reason_code"] == "NO_HEARTBEAT" for x in result["workers"])


def test_recent_healthy_and_stale_unreachable(health_app):
    now=datetime(2026,10,14,18,tzinfo=timezone.utc)
    db.session.add(_beat("track-scheduler", "a"*32, now))
    db.session.commit()
    assert _status(read_worker_health(now))["status"] == "HEALTHY"
    assert _status(read_worker_health(now+timedelta(seconds=210)))["status"] == "DEGRADED"
    assert _status(read_worker_health(now+timedelta(minutes=30)))["status"] == "UNREACHABLE"


def test_simultaneous_active_instances_are_degraded(health_app):
    now=datetime(2026,10,14,18,tzinfo=timezone.utc)
    db.session.add_all([
        _beat("marketing-scheduler", "a"*32, now),
        _beat("marketing-scheduler", "b"*32, now-timedelta(seconds=1)),
    ])
    db.session.commit()
    state=_status(read_worker_health(now),"marketing-scheduler")
    assert state["status"] == "DEGRADED"
    assert state["reason_code"] == "MULTIPLE_ACTIVE_INSTANCES"
    assert state["instance_count"] == 2


def test_disabled_and_clock_skew_do_not_report_healthy(health_app):
    now=datetime(2026,10,14,18,tzinfo=timezone.utc)
    db.session.add(_beat("routine-control-scheduler", "a"*32, now, enabled=False))
    db.session.add(_beat("track-scheduler", "b"*32, now+timedelta(minutes=4)))
    db.session.commit()
    assert _status(read_worker_health(now),"routine-control-scheduler")["status"] == "DISABLED"
    assert _status(read_worker_health(now))["reason_code"] == "CLOCK_SKEW"


def test_endpoint_requires_jwt_admicorp(health_app):
    with health_app.app_context():
        token=create_access_token(identity="47")
    client=health_app.test_client()
    path="/api/automation-control/workers/health"
    assert client.get(path).status_code == 401
    auth={"Authorization":f"Bearer {token}"}
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="SISTEMAS",rol="SISTEMAS")):
        assert client.get(path,headers=auth).status_code == 403
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="ADMICORP",rol="ADMINISTRADOR")):
        result=client.get(path,headers=auth)
    assert result.status_code == 200
    assert result.get_json()["coverage"] == "PERSISTED_WORKER_HEARTBEATS"


def test_invalid_emitter_arguments_and_fail_open(health_app):
    with pytest.raises(ValueError):
        emit_worker_heartbeat("invalid-worker", poll_interval_seconds=60)
    with pytest.raises(ValueError):
        emit_worker_heartbeat("track-scheduler", poll_interval_seconds=True)
    with patch.object(db.engine,"begin",side_effect=OSError("internal secret in driver")):
        emit_worker_heartbeat("track-scheduler", poll_interval_seconds=60)
    assert _status(read_worker_health())["status"] == "UNKNOWN"
