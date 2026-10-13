from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from app.extensions import db

from app.models.attendance import WarehouseAttendanceRunORM
from app.services.automation_control.job_catalog import get_job_catalog
from app.services.automation_control.job_read_service import (
    _serialize_attendance_run,
    has_run_source,
    list_job_runs,
)
from app.services.automation_control.timeline_service import _observations


@pytest.fixture
def flask_db_context():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)
    with app.app_context():
        yield


def _row(*, started_at_utc=None, trigger_source="REPORTS_SCHEDULER",
         status="SUCCESS", error_message=None, run_id=91):
    return SimpleNamespace(
        id=run_id,
        business_date=date(2026, 10, 12),
        trigger_source=trigger_source,
        status=status,
        error_message=error_message,
        source_sha256="sensitive-hash",
        started_at_utc=started_at_utc or datetime(2026, 10, 13, 13, 25, tzinfo=timezone.utc),
        finished_at_utc=datetime(2026, 10, 13, 13, 29, tzinfo=timezone.utc),
        source_rows=120, inserted_rows=95, updated_rows=20, rejected_rows=5,
    )


def _mock_query(rows):
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.return_value = rows
    return query


def test_attendance_is_cataloged_without_claiming_enabled():
    job = next(job for job in get_job_catalog()
               if job.key == "reports.attendance_daily_capture")
    assert job.worker_key == "reports-scheduler"
    assert job.enabled_default is False
    assert job.manual_run_supported is False
    assert "ATTENDANCE_DAILY_CAPTURE_ENABLED" in job.schedule_env_keys
    assert has_run_source(job.key)


def test_attendance_run_serialization_scrubs_sensitive_details():
    row = _row(status="FAILED", error_message="SECRET_SQL_OR_URL")
    result = _serialize_attendance_run(row)
    assert result["business_date"] == "2026-10-12"
    assert result["started_at_utc"] == "2026-10-13T13:25:00+00:00"
    assert result["status_raw"] == "FAILED"
    assert result["trigger_source"] == "REPORTS_SCHEDULER"
    assert result["error_available"] is True
    assert result["counts"]["source_rows"] == 120
    assert result["is_canonical"] is None
    assert "SECRET_SQL_OR_URL" not in str(result)
    assert "sensitive-hash" not in str(result)


def test_attendance_history_query_filters_manual_runs_and_paginates(flask_db_context):
    query = _mock_query([_row(run_id=1), _row(run_id=2), _row(run_id=3)])
    with patch.object(WarehouseAttendanceRunORM, "query", query):
        result = list_job_runs("reports.attendance_daily_capture", limit=2, offset=4)
    assert result["coverage"] == "DOMAIN_RUNS"
    assert [row["run_id"] for row in result["rows"]] == [1, 2]
    assert result["has_more"] is True
    query.offset.assert_called_with(4)
    query.limit.assert_called_with(3)
    conditions = [str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
                  for call in query.filter.call_args_list]
    assert any("REPORTS_SCHEDULER" in expression for expression in conditions)
    assert any("trigger_source" in expression for expression in conditions)


def test_attendance_timeline_filters_trigger_source_and_groups_local_time(flask_db_context):
    # 06:40 UTC del 14 de octubre sigue siendo 23:40 del 13 en Tijuana.
    row = _row(started_at_utc=datetime(2026, 10, 14, 6, 40, tzinfo=timezone.utc))
    query = _mock_query([row])
    with patch.object(WarehouseAttendanceRunORM, "query", query):
        result = _observations("reports.attendance_daily_capture", date(2026, 10, 13))
    assert len(result) == 1
    assert result[0]["observed_hour"] == "23:00"
    assert result[0]["observed_time"] == "23:40"
    assert result[0]["business_date"] == "2026-10-12"
    conditions = [str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
                  for call in query.filter.call_args_list]
    assert any("REPORTS_SCHEDULER" in expression for expression in conditions)
    assert any("started_at_utc" in expression for expression in conditions)


def test_attendance_no_history_is_not_success(flask_db_context):
    query = _mock_query([])
    with patch.object(WarehouseAttendanceRunORM, "query", query):
        result = list_job_runs("reports.attendance_daily_capture")
    assert result["rows"] == []
    assert result["coverage"] == "DOMAIN_RUNS"
    assert result["has_more"] is False
