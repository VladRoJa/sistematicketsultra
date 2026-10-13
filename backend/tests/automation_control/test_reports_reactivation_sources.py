from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from sqlalchemy.dialects import postgresql

from app.extensions import db
from app.models.warehouse import WarehouseAuditLogORM
from app.services.automation_control.job_catalog import get_job_catalog
from app.services.automation_control.job_read_service import (
    _filter_reports_completion,
    _serialize_reports_completion,
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


def _row(*, event_id=55, created_at=None, details=None):
    return SimpleNamespace(
        id=event_id,
        created_at=created_at or datetime(2026, 10, 13, 16, 35, tzinfo=timezone.utc),
        action="JOB_COMPLETED",
        performed_by_user_id=47,
        details=details if details is not None else {
            "source": "reports_scheduler",
            "job_key": "reactivation_sources_daily",
            "business_date": "2026-10-13",
            "status": "completed",
            "internal": "DO_NOT_EXPOSE",
        },
    )


def _mock_query(rows):
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.return_value = rows
    return query


def _sql_conditions(query):
    dialect = postgresql.dialect()
    return " | ".join(
        str(expression.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
        for call in query.filter.call_args_list
        for expression in call.args
    )


def test_catalog_has_only_completion_marker_and_optional_schedule():
    job = next(j for j in get_job_catalog()
               if j.key == "reports.reactivation_sources_daily")
    assert job.worker_key == "reports-scheduler"
    assert job.enabled_default is False
    assert job.manual_run_supported is False
    assert job.schedule_reference.startswith("09:00")
    assert has_run_source(job.key)


def test_audit_query_enforces_exact_source_job_status_and_action(flask_db_context):
    query = _mock_query([])
    _filter_reports_completion(query, job_key="reactivation_sources_daily")
    sql = _sql_conditions(query)
    for expected in (
        "JOB_COMPLETED",
        "reports_scheduler",
        "reactivation_sources_daily",
        "completed",
        "warehouse_audit_logs.details",
    ):
        assert expected in sql


def test_serialization_is_a_marker_not_an_invented_run():
    marker = _serialize_reports_completion(_row())
    assert marker["status_raw"] == "COMPLETED"
    assert marker["evidence_type"] == "COMPLETION_AUDIT"
    assert marker["business_date"] == "2026-10-13"
    assert marker["observed_at_utc"] == "2026-10-13T16:35:00+00:00"
    assert marker["started_at_utc"] is None
    assert marker["finished_at_utc"] is None
    assert marker["is_canonical"] is None
    assert marker["error_available"] is False
    assert "DO_NOT_EXPOSE" not in str(marker)
    assert "performed_by_user_id" not in marker


def test_invalid_business_date_is_not_invented():
    details = {"business_date": "NOT_A_DATE"}
    marker = _serialize_reports_completion(_row(details=details))
    assert marker["business_date"] is None


def test_history_is_paginated_and_cannot_claim_full_coverage(flask_db_context):
    query = _mock_query([_row(event_id=1), _row(event_id=2), _row(event_id=3)])
    with patch.object(WarehouseAuditLogORM, "query", query):
        result = list_job_runs("reports.reactivation_sources_daily", limit=2, offset=5)
    assert [record["run_id"] for record in result["rows"]] == [1, 2]
    assert result["has_more"] is True
    assert result["coverage"] == "COMPLETION_MARKERS_ONLY"
    query.offset.assert_called_once_with(5)
    query.limit.assert_called_once_with(3)
    sql = _sql_conditions(query)
    assert "JOB_COMPLETED" in sql
    assert "reactivation_sources_daily" in sql
    assert "reports_scheduler" in sql


def test_history_without_markers_is_empty_not_success(flask_db_context):
    query = _mock_query([])
    with patch.object(WarehouseAuditLogORM, "query", query):
        result = list_job_runs("reports.reactivation_sources_daily")
    assert result["rows"] == []
    assert result["coverage"] == "COMPLETION_MARKERS_ONLY"


def test_timeline_uses_audit_record_time_in_tijuana(flask_db_context):
    # 06:35 UTC equivale a 23:35 del día anterior en Tijuana.
    row = _row(created_at=datetime(2026, 10, 14, 6, 35, tzinfo=timezone.utc))
    query = _mock_query([row])
    with patch.object(WarehouseAuditLogORM, "query", query):
        rows = _observations("reports.reactivation_sources_daily", date(2026, 10, 13))
    assert len(rows) == 1
    assert rows[0]["observed_hour"] == "23:00"
    assert rows[0]["observed_time"] == "23:35"
    assert rows[0]["evidence_type"] == "COMPLETION_AUDIT"
    assert "warehouse_audit_logs.created_at" in _sql_conditions(query)
    assert "reactivation_sources_daily" in _sql_conditions(query)


def test_naive_audit_time_does_not_imply_timezone(flask_db_context):
    row = _row(created_at=datetime(2026, 10, 13, 9))
    query = _mock_query([row])
    with patch.object(WarehouseAuditLogORM, "query", query):
        rows = _observations("reports.reactivation_sources_daily", date(2026, 10, 13))
    assert rows == []
