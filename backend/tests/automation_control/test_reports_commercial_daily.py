"""Reportes comerciales: marcador de finalización y hora nominal bloqueada por Track."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from sqlalchemy.dialects import postgresql

from app.extensions import db
from app.models.warehouse import WarehouseAuditLogORM
from app.routes.automation_control_routes import _job_metadata
from app.services.automation_control.job_catalog import get_job_catalog
from app.services.automation_control.job_read_service import (
    has_completion_marker_source, list_job_runs,
)
from app.services.automation_control.timeline_service import _observations, daily_timeline
from app.warehouse.services.scheduler_priority_service import is_secondary_execution_window


@pytest.fixture
def context():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)
    with app.app_context():
        yield


def _query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = rows
    return q


def _where(q):
    return " | ".join(
        str(expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        ))
        for call in q.filter.call_args_list for expr in call.args
    )


def _row(stamp):
    return SimpleNamespace(
        id=451,
        created_at=stamp,
        details={
            "source": "reports_scheduler",
            "job_key": "commercial_daily_reports",
            "status": "completed",
            "business_date": "2026-10-12",
            "secrets": "DO_NOT_LEAK",
        },
        performed_by_user_id=47,
    )


def test_catalog_describes_nominal_slot_gating_and_previous_day():
    job = next(j for j in get_job_catalog()
               if j.key == "reports.commercial_daily_reports")
    assert job.worker_key == "reports-scheduler"
    assert job.schedule_kind == "DAILY_TIME_OPTIONAL_GATED"
    assert "01:20" in job.schedule_reference
    assert "05:20" in job.schedule_reference
    assert "día anterior" in job.schedule_reference
    assert job.enabled_default is False
    assert job.manual_run_supported is False
    assert set(job.schedule_env_keys) == {
        "COMMERCIAL_DAILY_REPORTS_ENABLED",
        "COMMERCIAL_DAILY_REPORTS_RUN_HOUR",
        "COMMERCIAL_DAILY_REPORTS_RUN_MINUTE",
    }
    assert has_completion_marker_source(job.key)
    info = _job_metadata(job)
    assert info["run_history_coverage"] == "COMPLETION_MARKERS_ONLY"
    assert info["effective_enabled"] is None
    assert info["worker_health"] == "UNKNOWN"


def test_0120_is_not_eligible_but_0520_is_eligible_window():
    assert not is_secondary_execution_window(datetime(2026, 10, 13, 1, 20))
    assert not is_secondary_execution_window(datetime(2026, 10, 13, 5, 19))
    assert is_secondary_execution_window(datetime(2026, 10, 13, 5, 20))
    assert is_secondary_execution_window(datetime(2026, 10, 13, 22, 44))
    assert not is_secondary_execution_window(datetime(2026, 10, 13, 22, 45))
    # Corresponde al corte de ayer; no crear un horario exigible 01:20.
    with patch("app.services.automation_control.timeline_service._observations", return_value=[]):
        result = daily_timeline(date(2026, 10, 13))
    jobs = (job for worker in result["workers"] for job in worker["jobs"])
    monitored = next(j for j in jobs if j["job_key"] == "reports.commercial_daily_reports")
    assert monitored["reference_slots"] == []
    assert monitored["schedule_verified"] is False
    assert monitored["coverage"] == "COMPLETION_MARKERS_ONLY"


def test_history_selects_only_commercial_scheduler_completion_and_scrubs(context):
    audit = _row(datetime(2026, 10, 13, 12, 55, tzinfo=timezone.utc))
    q = _query([audit, audit])
    with patch.object(WarehouseAuditLogORM, "query", q):
        result = list_job_runs("reports.commercial_daily_reports", limit=1, offset=3)
    assert result["coverage"] == "COMPLETION_MARKERS_ONLY"
    assert result["has_more"] is True
    q.limit.assert_called_once_with(2)
    q.offset.assert_called_once_with(3)
    sql = _where(q)
    for token in ("JOB_COMPLETED", "reports_scheduler",
                  "commercial_daily_reports", "completed"):
        assert token in sql
    assert "'reactivation_sources_daily'" not in sql
    assert "'cobranza_recurrente_rechazados'" not in sql
    observation = result["rows"][0]
    assert observation["evidence_type"] == "COMPLETION_AUDIT"
    assert observation["business_date"] == "2026-10-12"
    assert observation["observed_at_utc"] == "2026-10-13T12:55:00+00:00"
    assert observation["started_at_utc"] is None
    assert observation["finished_at_utc"] is None
    assert observation["error_available"] is False
    assert "DO_NOT_LEAK" not in str(observation)


def test_timeline_uses_completion_audit_time_not_previous_business_date(context):
    # 12:55 UTC del 13 corresponde a 05:55 del 13 en Tijuana.
    audit = _row(datetime(2026, 10, 13, 12, 55, tzinfo=timezone.utc))
    q = _query([audit])
    with patch.object(WarehouseAuditLogORM, "query", q):
        rows = _observations("reports.commercial_daily_reports", date(2026, 10, 13))
    assert len(rows) == 1
    assert rows[0]["business_date"] == "2026-10-12"
    assert rows[0]["observed_hour"] == "05:00"
    assert rows[0]["observed_time"] == "05:55"
    assert rows[0]["evidence_type"] == "COMPLETION_AUDIT"
    assert "'commercial_daily_reports'" in _where(q)
    assert "warehouse_audit_logs.created_at" in _where(q)


def test_absent_audit_does_not_mean_failed(context):
    q = _query([])
    with patch.object(WarehouseAuditLogORM, "query", q):
        result = list_job_runs("reports.commercial_daily_reports")
    assert result["rows"] == []
    assert result["coverage"] == "COMPLETION_MARKERS_ONLY"
    assert result["has_more"] is False


def test_unknown_timezone_is_not_invented(context):
    q = _query([_row(datetime(2026, 10, 13, 13, 15))])
    with patch.object(WarehouseAuditLogORM, "query", q):
        rows = _observations("reports.commercial_daily_reports", date(2026, 10, 13))
    assert rows == []
