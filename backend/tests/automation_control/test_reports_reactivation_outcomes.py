"""Cobertura aislada: resultados de reactivación, auditados por reports-scheduler."""
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
    has_completion_marker_source, has_run_source, list_job_runs,
)
from app.services.automation_control.timeline_service import _observations


@pytest.fixture
def flask_context():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)
    with app.app_context():
        yield


def _row(event_id=81, stamp=None):
    return SimpleNamespace(
        id=event_id,
        created_at=stamp or datetime(2026, 10, 13, 16, 28, tzinfo=timezone.utc),
        details={
            "source": "reports_scheduler",
            "job_key": "reactivation_outcomes_daily",
            "status": "completed",
            "business_date": "2026-10-13",
            "private": "NEVER_RETURN_THIS",
        },
        performed_by_user_id=47,
    )


def _query(rows):
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.return_value = rows
    return query


def _where_sql(query):
    return " | ".join(
        str(expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        ))
        for call in query.filter.call_args_list for expr in call.args
    )


def test_outcomes_catalog_and_exact_dependency():
    job = next(
        j for j in get_job_catalog()
        if j.key == "reports.reactivation_outcomes_daily"
    )
    assert job.worker_key == "reports-scheduler"
    assert job.schedule_kind == "DAILY_TIME_OPTIONAL"
    assert job.schedule_reference.startswith("09:15")
    assert job.enabled_default is False
    assert job.manual_run_supported is False
    assert set(job.schedule_env_keys) == {
        "REACTIVATION_SOURCES_ENABLED",
        "REACTIVATION_OUTCOMES_RUN_HOUR",
        "REACTIVATION_OUTCOMES_RUN_MINUTE",
    }


def test_both_reactivation_jobs_have_separate_audit_coverage():
    assert has_run_source("reports.reactivation_sources_daily")
    assert has_run_source("reports.reactivation_outcomes_daily")
    assert has_completion_marker_source("reports.reactivation_sources_daily")
    assert has_completion_marker_source("reports.reactivation_outcomes_daily")
    assert not has_completion_marker_source("reports.attendance_daily_capture")
    assert not has_completion_marker_source("track.preview_operativo")
    outcomes = next(
        j for j in get_job_catalog()
        if j.key == "reports.reactivation_outcomes_daily"
    )
    info = _job_metadata(outcomes)
    assert info["run_history_coverage"] == "COMPLETION_MARKERS_ONLY"
    assert info["worker_health"] == "UNKNOWN"
    assert info["effective_enabled"] is None


def test_outcomes_history_filters_strict_job_and_paginates(flask_context):
    q = _query([_row(81), _row(82), _row(83)])
    with patch.object(WarehouseAuditLogORM, "query", q):
        result = list_job_runs("reports.reactivation_outcomes_daily", limit=2, offset=5)
    assert result["coverage"] == "COMPLETION_MARKERS_ONLY"
    assert [x["run_id"] for x in result["rows"]] == [81, 82]
    assert result["has_more"] is True
    q.offset.assert_called_once_with(5)
    q.limit.assert_called_once_with(3)
    where = _where_sql(q)
    for required in ("JOB_COMPLETED", "reports_scheduler",
                     "reactivation_outcomes_daily", "completed"):
        assert required in where
    assert "'reactivation_sources_daily'" not in where
    assert result["rows"][0]["started_at_utc"] is None
    assert result["rows"][0]["finished_at_utc"] is None
    assert result["rows"][0]["observed_at_utc"] == "2026-10-13T16:28:00+00:00"
    assert "NEVER_RETURN_THIS" not in str(result)


def test_outcomes_timeline_uses_local_audit_time_not_schedule(flask_context):
    # 06:29 UTC del día siguiente es 23:29 del 13 de octubre en Tijuana.
    row = _row(stamp=datetime(2026, 10, 14, 6, 29, tzinfo=timezone.utc))
    q = _query([row])
    with patch.object(WarehouseAuditLogORM, "query", q):
        entries = _observations("reports.reactivation_outcomes_daily", date(2026, 10, 13))
    assert len(entries) == 1
    assert entries[0]["observed_hour"] == "23:00"
    assert entries[0]["observed_time"] == "23:29"
    assert entries[0]["evidence_type"] == "COMPLETION_AUDIT"
    where = _where_sql(q)
    assert "'reactivation_outcomes_daily'" in where
    assert "'reactivation_sources_daily'" not in where
    assert "warehouse_audit_logs.created_at" in where


def test_missing_completion_is_unknown_not_failure(flask_context):
    q = _query([])
    with patch.object(WarehouseAuditLogORM, "query", q):
        res = list_job_runs("reports.reactivation_outcomes_daily")
    assert res["coverage"] == "COMPLETION_MARKERS_ONLY"
    assert res["rows"] == []
    assert res["has_more"] is False


def test_audit_time_without_timezone_does_not_get_invented(flask_context):
    row = _row(stamp=datetime(2026, 10, 13, 9, 30))
    q = _query([row])
    with patch.object(WarehouseAuditLogORM, "query", q):
        entries = _observations("reports.reactivation_outcomes_daily", date(2026, 10, 13))
    assert entries == []
