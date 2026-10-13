"""Diagnósticos legacy: correlación estricta, sin texto crudo y permisos backend."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy.dialects import postgresql

from app.extensions import db
from app.models.attendance import WarehouseAttendanceRunORM
from app.models.routine_control import RoutineControlPipelineRunORM
from app.routes.automation_control_routes import automation_control_bp
from app.services.automation_control.diagnostic_service import (
    _attributed_query, last_error_diagnostic, run_diagnostic,
)


@pytest.fixture
def api():
    app=Flask(__name__)
    app.config.update(TESTING=True,JWT_SECRET_KEY="only-test")
    JWTManager(app)
    app.register_blueprint(automation_control_bp,url_prefix="/api/automation-control")
    with app.app_context():
        jwt=create_access_token(identity="47")
    return app.test_client(),{"Authorization":f"Bearer {jwt}"}


@pytest.fixture
def flask_db():
    app=Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"]="sqlite:///:memory:"
    db.init_app(app)
    with app.app_context():
        yield


def _row():
    return WarehouseAttendanceRunORM(
        id=11,business_date=date(2026,10,13),
        status="FAILED",trigger_source="REPORTS_SCHEDULER",
        started_at_utc=datetime(2026,10,13,14,0,tzinfo=timezone.utc),
        finished_at_utc=datetime(2026,10,13,14,1,tzinfo=timezone.utc),
        error_message="Bearer TOKEN_PRIVATE https://signed-url/",
        source_sha256="sensitive_sha",
    )


def _mock_query(rows):
    q=MagicMock()
    for name in ("filter","order_by","limit"):
        getattr(q,name).return_value=q
    q.first.return_value=rows[0] if rows else None
    return q


def _where(query):
    return " | ".join(str(e.compile(
        dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True}
    )) for c in query.filter.call_args_list for e in c.args)


def test_api_denies_without_jwt_and_non_admicorp(api):
    client,headers=api
    paths=[
        "/api/automation-control/jobs/reports.attendance_daily_capture/runs/11/diagnostic",
        "/api/automation-control/jobs/reports.attendance_daily_capture/last-error",
    ]
    for p in paths:
        assert client.get(p).status_code==401
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="SISTEMAS",rol="SISTEMAS")):
        for p in paths:
            assert client.get(p,headers=headers).status_code==403


def test_api_unknown_job_bad_date_scope_and_missing_run(api):
    client,headers=api
    with (patch("app.routes.automation_control_routes.UserORM.get_by_id",
                return_value=SimpleNamespace(username="ADMICORP")),
          patch("app.routes.automation_control_routes.run_diagnostic",
                return_value=None)):
        assert client.get("/api/automation-control/jobs/unknown/last-error",
                          headers=headers).status_code==404
        assert client.get("/api/automation-control/jobs/reports.attendance_daily_capture/last-error?business_date=bad",
                          headers=headers).status_code==400
        assert client.get("/api/automation-control/jobs/reports.attendance_daily_capture/last-error?scope_key=BRANCH_1",
                          headers=headers).status_code==400
        assert client.get("/api/automation-control/jobs/reports.attendance_daily_capture/runs/12/diagnostic",
                          headers=headers).status_code==404


def test_safe_diagnostic_drops_all_raw_error_data(flask_db):
    q=_mock_query([_row()])
    with patch.object(WarehouseAttendanceRunORM,"query",q):
        detail=run_diagnostic("reports.attendance_daily_capture",11)
    assert detail["job_key"]=="reports.attendance_daily_capture"
    assert detail["run_id"]==11
    assert detail["status"]=="FAILED"
    assert detail["diagnostic_state"]=="LOG_NOT_AVAILABLE"
    assert detail["log_lines"]==[]
    assert detail["started_at_utc"]=="2026-10-13T14:00:00+00:00"
    assert "TOKEN_PRIVATE" not in str(detail)
    assert "signed-url" not in str(detail)
    assert "sensitive_sha" not in str(detail)
    assert "REPORTS_SCHEDULER" in _where(q)
    assert "warehouse_attendance_runs.id = 11" in _where(q)


def test_instrumentation_missing_does_not_lookup_other_job(flask_db):
    assert run_diagnostic("tickets.attachment_cleanup",13) is None
    detail=last_error_diagnostic("reports.commercial_daily_reports")
    assert detail["diagnostic_state"]=="LOG_NOT_AVAILABLE"
    assert detail["run_id"] is None


def test_routine_query_requires_generation_mode_and_trigger_prefix(flask_db):
    q=_mock_query([])
    with patch.object(RoutineControlPipelineRunORM,"query",q):
        model,_=_attributed_query("routine_control.scheduled_pipeline")
    assert model is RoutineControlPipelineRunORM
    where=_where(q)
    assert "generation_mode = 'SCHEDULED'" in where
    assert "'ROUTINE_CONTROL_SCHEDULER_'" in where


def test_last_error_uses_failure_and_business_date_filters(flask_db):
    q=_mock_query([_row()])
    with patch.object(WarehouseAttendanceRunORM,"query",q):
        detail=last_error_diagnostic("reports.attendance_daily_capture",
                                     business_date=date(2026,10,13))
    assert detail["run_id"]==11
    assert detail["failure_recency"]=="HISTORICAL_OR_ACTIVE_UNVERIFIED"
    where=_where(q)
    assert "warehouse_attendance_runs.business_date = '2026-10-13'" in where
    assert "FAILED" in where
    assert "REPORTS_SCHEDULER" in where


def test_failing_run_without_raw_error_does_not_invent_log(flask_db):
    row=_row()
    row.error_message=None
    q=_mock_query([row])
    with patch.object(WarehouseAttendanceRunORM,"query",q):
        result=run_diagnostic("reports.attendance_daily_capture",11)
    assert result["diagnostic_state"]=="LOG_NOT_AVAILABLE"
    assert result["error_code"] is None
    assert result["log_state"] == "LOG_NOT_AVAILABLE"
