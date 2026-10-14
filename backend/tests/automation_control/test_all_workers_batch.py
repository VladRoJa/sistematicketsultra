"""Monitor de rutinas: atribución estricta por generación y trigger, sin logs sensibles."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from sqlalchemy.dialects import postgresql

from app.extensions import db
from app.models.routine_control import RoutineControlPipelineRunORM
from app.services.automation_control.job_catalog import get_job_catalog
from app.services.automation_control.job_read_service import (
    _serialize_routine_pipeline_run, list_job_runs,
)
from app.services.automation_control.timeline_service import _observations, daily_timeline


@pytest.fixture
def app_context():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)
    with app.app_context():
        yield


def _row(**kw):
    data = {
        "id": 903,
        "business_date": date(2026, 10, 13),
        "generation_mode": "SCHEDULED",
        "trigger_source": "ROUTINE_CONTROL_SCHEDULER_09_20",
        "created_at": datetime(2026, 10, 13, 16, 22, tzinfo=timezone.utc),
        "started_at_utc": datetime(2026, 10, 13, 16, 24, tzinfo=timezone.utc),
        "finished_at_utc": datetime(2026, 10, 13, 16, 27, tzinfo=timezone.utc),
        "status": "PARTIAL",
        "error_message": "PRIVATE_URL_OR_PASSWORD",
        "error_code": "SAFE_NO_EXPORT",
        "members_created": 8,
        "members_updated": 3,
        "incidents_created": 1,
        "records_rejected": 2,
        "worker_instance_id": "SECRET_WORKER_INSTANCE",
    }
    data.update(kw)
    return SimpleNamespace(**data)


def _query(rows):
    q = MagicMock()
    for name in ("filter", "order_by", "offset", "limit"):
        getattr(q, name).return_value = q
    q.all.return_value = rows
    return q


def _compiled(q):
    return " | ".join(
        str(a.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for call in q.filter.call_args_list for a in call.args
    )


def test_catalog_five_workers_without_fabricated_health():
    jobs = get_job_catalog()
    assert len(jobs) == 18
    keys = {job.key for job in jobs}
    assert "routine_control.scheduled_pipeline" in keys
    assert "reports.reporte_direccion_daily_capture" in keys
    assert "tickets.attachment_cleanup" in keys
    assert all(j.manual_run_supported is False for j in jobs)
    routine = next(j for j in jobs if j.key == "routine_control.scheduled_pipeline")
    assert "ROUTINE_CONTROL_RUN_TIMES" in routine.schedule_env_keys
    assert "09:20" in routine.schedule_reference
    assert routine.evidence_tables == ("routine_control_pipeline_runs",)


def test_manual_and_backfill_cannot_be_matched_by_filter(app_context):
    q = _query([])
    with patch.object(RoutineControlPipelineRunORM, "query", q):
        list_job_runs("routine_control.scheduled_pipeline")
    sql = _compiled(q)
    assert "routine_control_pipeline_runs.generation_mode = 'SCHEDULED'" in sql
    assert "substr(" in sql
    assert "'ROUTINE_CONTROL_SCHEDULER_'" in sql
    assert "routine_control_pipeline_runs.trigger_source" in sql


def test_history_paginates_and_scrubs_errors(app_context):
    q = _query([_row(id=1), _row(id=2), _row(id=3)])
    with patch.object(RoutineControlPipelineRunORM, "query", q):
        result = list_job_runs("routine_control.scheduled_pipeline", limit=2, offset=3)
    assert result["coverage"] == "DOMAIN_RUNS"
    assert [x["run_id"] for x in result["rows"]] == [1, 2]
    assert result["has_more"] is True
    assert result["rows"][0]["status_raw"] == "PARTIAL"
    assert result["rows"][0]["trigger_source"] == "ROUTINE_CONTROL_SCHEDULER_09_20"
    assert result["rows"][0]["error_available"] is True
    assert result["rows"][0]["counts"]["members_created"] == 8
    assert result["rows"][0]["counts"]["records_rejected"] == 2
    assert "PRIVATE_URL_OR_PASSWORD" not in str(result)
    assert "SECRET_WORKER_INSTANCE" not in str(result)
    assert "SAFE_NO_EXPORT" not in str(result)
    q.offset.assert_called_once_with(3)
    q.limit.assert_called_once_with(3)


def test_timeline_uses_created_at_even_when_no_start(app_context):
    row = _row(
        created_at=datetime(2026, 10, 14, 6, 35, tzinfo=timezone.utc),
        started_at_utc=None, finished_at_utc=None, status="PENDING",
    )
    q = _query([row])
    with patch.object(RoutineControlPipelineRunORM, "query", q):
        observations = _observations("routine_control.scheduled_pipeline", date(2026, 10, 13))
    assert len(observations) == 1
    assert observations[0]["observed_hour"] == "23:00"
    assert observations[0]["observed_time"] == "23:35"
    assert observations[0]["started_at_utc"] is None
    assert observations[0]["status_raw"] == "PENDING"
    sql = _compiled(q)
    assert "routine_control_pipeline_runs.created_at" in sql
    assert "generation_mode = 'SCHEDULED'" in sql


def test_missing_runs_no_false_success(app_context):
    q = _query([])
    with patch.object(RoutineControlPipelineRunORM, "query", q):
        result = list_job_runs("routine_control.scheduled_pipeline")
    assert result["coverage"] == "DOMAIN_RUNS"
    assert result["rows"] == []
    assert result["has_more"] is False


def test_unattributable_direction_and_ticket_stay_not_instrumented():
    with patch("app.services.automation_control.timeline_service._observations", return_value=[]):
        result = daily_timeline(date(2026, 10, 13))
    lookup = {j["job_key"]: j for w in result["workers"] for j in w["jobs"]}
    for key in ("reports.reporte_direccion_daily_capture", "tickets.attachment_cleanup"):
        assert lookup[key]["coverage"] == "NOT_INSTRUMENTED"
        assert lookup[key]["reference_slots"] == []
        assert lookup[key]["observed"] == {}
