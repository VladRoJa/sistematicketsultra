from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes.automation_control_routes import automation_control_bp
from app.services.automation_control.timeline_service import (
    _local_start, daily_timeline,
)


@pytest.fixture
def api():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="timeline-tests-only")
    JWTManager(app)
    app.register_blueprint(automation_control_bp, url_prefix="/api/automation-control")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_local_conversion_uses_tijuana_and_rejects_naive():
    stamp = datetime(2026, 10, 13, 18, 0, tzinfo=timezone.utc)
    assert _local_start(stamp).hour == 11
    assert _local_start(datetime(2026, 10, 13, 11)) is None


def test_reference_schedule_is_never_verified():
    with patch("app.services.automation_control.timeline_service._observations", return_value=[]):
        result = daily_timeline(date(2026, 10, 13))
    assert result["schedule_verified"] is False
    assert result["timezone"] == "America/Tijuana"
    assert len(result["workers"]) == 5
    reports = next(w for w in result["workers"] if w["worker_key"] == "reports-scheduler")
    assert len(reports["jobs"]) == 6
    assert reports["jobs"][0]["reference_slots"] == ["09:00"] or any(
        j["reference_slots"] == ["09:00"] for j in reports["jobs"]
    )
    assert any(j["reference_slots"] == ["06:20"] for j in reports["jobs"])
    assert any(
        j["job_key"] == "reports.commercial_daily_reports"
        and j["reference_slots"] == []
        and j["coverage"] == "COMPLETION_MARKERS_ONLY"
        and j["schedule_verified"] is False
        for j in reports["jobs"]
    )
    assert any(
        j["job_key"] == "reports.cobranza_recurrente_rechazados"
        and j["reference_slots"] == ["08:00"]
        and j["schedule_verified"] is False
        and j["coverage"] == "COMPLETION_MARKERS_ONLY"
        for j in reports["jobs"]
    )
    assert any(
        j["job_key"] == "reports.reactivation_outcomes_daily"
        and j["reference_slots"] == ["09:15"]
        and j["schedule_verified"] is False
        for j in reports["jobs"]
    )
    assert any(
        j["job_key"] == "reports.reporte_direccion_daily_capture"
        and j["coverage"] == "NOT_INSTRUMENTED"
        and j["reference_slots"] == []
        for j in reports["jobs"]
    )
    routine = next(w for w in result["workers"]
                   if w["worker_key"] == "routine-control-scheduler")
    assert len(routine["jobs"]) == 1
    assert routine["jobs"][0]["reference_slots"] == [
        "09:20", "13:20", "17:20", "21:20",
    ]
    cleanup = next(w for w in result["workers"]
                   if w["worker_key"] == "ticket-attachment-cleanup")
    assert len(cleanup["jobs"]) == 1
    assert cleanup["jobs"][0]["coverage"] == "NOT_INSTRUMENTED"
    assert cleanup["jobs"][0]["reference_slots"] == []
    assert reports["jobs"][0]["schedule_verified"] is False
    assert next(job for worker in result["workers"] for job in worker["jobs"]
                if job["job_key"] == "marketing.iventas_sync")["reference_slots"] == [
                    "08:20", "12:20", "16:20", "20:20"
                ]


def test_not_instrumented_cannot_be_reported_as_success():
    with patch("app.services.automation_control.timeline_service._observations", return_value=[]):
        result = daily_timeline(date(2026, 10, 13))
    missing = next(job for worker in result["workers"] for job in worker["jobs"]
                   if job["job_key"] == "track.warehouse_retention")
    assert missing["coverage"] == "NOT_INSTRUMENTED"
    assert missing["observed"] == {}


def test_runs_grouped_by_observed_hour_not_claimed_schedule():
    item = {"run_id": 100, "observed_hour": "08:00", "observed_time": "08:23",
            "status_raw": "COMPLETED"}
    with patch("app.services.automation_control.timeline_service._observations",
               side_effect=lambda key, day: [item] if key == "marketing.iventas_sync" else []):
        result = daily_timeline(date(2026, 10, 13))
    job = next(job for worker in result["workers"] for job in worker["jobs"]
               if job["job_key"] == "marketing.iventas_sync")
    assert job["observed"] == {"08:00": [item]}


def test_jwt_and_admicorp_are_required(api):
    client, headers = api
    assert client.get("/api/automation-control/timeline").status_code == 401
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="SISTEMAS", rol="SISTEMAS")):
        assert client.get("/api/automation-control/timeline", headers=headers).status_code == 403


def test_invalid_date_returns_400(api):
    client, headers = api
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="ADMICORP", rol="ADMINISTRADOR")):
        assert client.get("/api/automation-control/timeline?date=2026-99-99",
                          headers=headers).status_code == 400


def test_valid_date_delegates_to_service(api):
    client, headers = api
    result = {"date": "2026-10-13", "timezone": "America/Tijuana",
              "workers": [], "schedule_verified": False}
    with (patch("app.routes.automation_control_routes.UserORM.get_by_id",
                return_value=SimpleNamespace(username="ADMICORP", rol="ADMINISTRADOR")),
          patch("app.routes.automation_control_routes.daily_timeline",
                return_value=result) as reader):
        response = client.get("/api/automation-control/timeline?date=2026-10-13",
                              headers=headers)
    assert response.status_code == 200
    assert response.get_json()["schedule_verified"] is False
    reader.assert_called_once_with(date(2026, 10, 13))
