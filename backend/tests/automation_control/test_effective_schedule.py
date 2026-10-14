"""Effective worker schedules are opt-in, scoped, sanitized and never guaranteed runs."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.extensions import db
from app.models.automation_control import SystemWorkerHeartbeatORM as Beat
from app.routes.automation_control_routes import automation_control_bp
from app.services.automation_control.effective_schedule_service import (
    read_effective_schedules, validate_schedule_snapshot, schedule_spec,
)

UTC = timezone.utc
NOW = datetime(2026, 10, 14, 18, tzinfo=UTC)
SPEC = schedule_spec(
    enabled=True,timezone_name="America/Tijuana",kind="DAILY_TIME",
    slots=["23:30"],conditional=False,
)


@pytest.fixture
def appdb():
    app=Flask(__name__)
    app.config.update(TESTING=True,SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
                      JWT_SECRET_KEY="synthetic-qa-only")
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(automation_control_bp,url_prefix="/api/automation-control")
    with app.app_context():
        Beat.__table__.create(db.engine)
        yield app
        db.session.remove()


def _beat(key,config,instance="a"*32,seen=NOW):
    db.session.add(Beat(
        worker_key=key,instance_id=instance,
        started_at=seen-timedelta(hours=1),
        last_seen_at=seen,poll_interval_seconds=60,enabled=True,
        job_schedules=config,
    ))
    db.session.commit()


def _job(result, key="track.base_nocturna_canonica"):
    return next(x for x in result["jobs"] if x["job_key"]==key)


def test_unknown_without_heartbeats(appdb):
    x=read_effective_schedules(NOW)
    assert len(x["jobs"])==18
    assert all(j["state"]=="UNVERIFIED" and j["next_due_at"] is None for j in x["jobs"])


def test_exact_attestation_only_not_other_jobs(appdb):
    _beat("track-scheduler",{"track.base_nocturna_canonica":SPEC})
    x=read_effective_schedules(NOW)
    assert _job(x)["state"]=="REPORTED"
    assert _job(x)["schedule"]["slots"]==["23:30"]
    assert _job(x)["next_due_at"] is None
    assert _job(x,"track.preview_operativo")["state"]=="UNVERIFIED"
    assert _job(x,"marketing.iventas_sync")["state"]=="UNVERIFIED"


def test_stale_or_multiple_instances_never_reuse_runtime_config(appdb):
    _beat("track-scheduler",{"track.base_nocturna_canonica":SPEC})
    assert _job(read_effective_schedules(NOW+timedelta(minutes=30)))["state"]=="UNVERIFIED"
    _beat("track-scheduler",{"track.base_nocturna_canonica":SPEC},instance="b"*32)
    assert _job(read_effective_schedules(NOW))["state"]=="UNVERIFIED"


def test_disabled_flag_is_explicit(appdb):
    value=schedule_spec(enabled=False,timezone_name="America/Tijuana",
                        kind="INTERVAL",conditional=True)
    _beat("marketing-scheduler",{"marketing.campaign_v2_provider_stats":value})
    j=_job(read_effective_schedules(NOW),"marketing.campaign_v2_provider_stats")
    assert j["state"]=="DISABLED"
    assert j["schedule"]["enabled"] is False


@pytest.mark.parametrize("data",[
    {"marketing.iventas_sync":SPEC},
    {"track.base_nocturna_canonica":{**SPEC,"credentials":"SECRET"}},
    {"track.base_nocturna_canonica":{**SPEC,"timezone":"Bearer SECRET"}},
    {"track.base_nocturna_canonica":{**SPEC,"slots":["garbage"]}},
    {"track.base_nocturna_canonica":{**SPEC,"enabled":"true"}},
    {"track.base_nocturna_canonica":{**SPEC,"kind":[]}},
    {"track.base_nocturna_canonica":{**SPEC,"interval_seconds":True}},
    {"track.base_nocturna_canonica":{**SPEC,"slots":[]}},
])
def test_unsafe_or_unmatched_data_rejected(data):
    with pytest.raises(ValueError):
        validate_schedule_snapshot("track-scheduler",data)


def test_malformed_stored_evidence_is_not_exposed(appdb):
    _beat("track-scheduler",{"track.base_nocturna_canonica":{**SPEC,"raw":"SECRET"}})
    j=_job(read_effective_schedules(NOW))
    assert j["state"]=="UNVERIFIED"
    assert j["reason_code"]=="INVALID_SCHEDULE_SNAPSHOT"
    assert "SECRET" not in str(j)


def test_endpoint_jwt_and_admicorp_only(appdb):
    with appdb.app_context():
        token=create_access_token(identity="47")
    c=appdb.test_client()
    url="/api/automation-control/jobs/effective-schedules"
    assert c.get(url).status_code==401
    auth={"Authorization": "Bearer "+token}
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="SISTEMAS",rol="SISTEMAS")):
        assert c.get(url,headers=auth).status_code==403
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="ADMICORP",rol="ADMINISTRADOR")):
        result=c.get(url,headers=auth)
    assert result.status_code==200
    assert len(result.get_json()["jobs"])==18


def test_query_returns_single_newest_heartbeat_after_many_restarts(appdb):
    for i in range(25):
        _beat(
            "track-scheduler",
            {"track.base_nocturna_canonica":{**SPEC,"slots":["01:10"]}},
            instance=f"{i:032x}",
            seen=NOW-timedelta(days=i+1),
        )
    _beat("track-scheduler", {"track.base_nocturna_canonica":SPEC},
          instance="f"*32, seen=NOW)
    result=_job(read_effective_schedules(NOW))
    assert result["state"]=="REPORTED"
    assert result["schedule"]["slots"]==["23:30"]
