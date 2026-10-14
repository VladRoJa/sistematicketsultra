"""Cobranza recurrente: evidencia acotada de finalización del reports-scheduler."""
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
    has_completion_marker_source, list_job_runs,
)
from app.services.automation_control.timeline_service import _observations


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
        id=311,
        created_at=stamp,
        details={
            "source": "reports_scheduler",
            "job_key": "cobranza_recurrente_rechazados",
            "status": "completed",
            "business_date": "2026-10-13",
            "internal": "SENSITIVE_VALUE",
        },
        performed_by_user_id=47,
    )


def test_catalog_has_optional_disabled_reference():
    job = next(j for j in get_job_catalog()
               if j.key == "reports.cobranza_recurrente_rechazados")
    assert job.worker_key == "reports-scheduler"
    assert job.schedule_reference.startswith("08:00")
    assert job.enabled_default is False
    assert job.manual_run_supported is False
    assert set(job.schedule_env_keys) == {
        "COBRANZA_RECURRENTE_ENABLED",
        "COBRANZA_RECURRENTE_RUN_HOUR",
        "COBRANZA_RECURRENTE_RUN_MINUTE",
    }
    assert has_completion_marker_source(job.key)


def test_history_filter_is_exact_and_no_raw_payload(context):
    row = _row(datetime(2026, 10, 13, 16, 24, tzinfo=timezone.utc))
    q = _query([row, row])
    with patch.object(WarehouseAuditLogORM, "query", q):
        result = list_job_runs("reports.cobranza_recurrente_rechazados", limit=1, offset=2)
    assert result["coverage"] == "COMPLETION_MARKERS_ONLY"
    assert result["has_more"] is True
    q.limit.assert_called_once_with(2)
    q.offset.assert_called_once_with(2)
    where = _where(q)
    assert "JOB_COMPLETED" in where
    assert "'reports_scheduler'" in where
    assert "'cobranza_recurrente_rechazados'" in where
    assert "'completed'" in where
    assert "'reactivation_sources_daily'" not in where
    assert "'reactivation_outcomes_daily'" not in where
    entry = result["rows"][0]
    assert entry["evidence_type"] == "COMPLETION_AUDIT"
    assert entry["started_at_utc"] is None
    assert entry["finished_at_utc"] is None
    assert entry["observed_at_utc"] == "2026-10-13T16:24:00+00:00"
    assert "SENSITIVE_VALUE" not in str(entry)


def test_timeline_uses_completion_time_not_reference_slot(context):
    # 06:25 UTC del 14 = 23:25 del 13, hora Tijuana.
    row = _row(datetime(2026, 10, 14, 6, 25, tzinfo=timezone.utc))
    q = _query([row])
    with patch.object(WarehouseAuditLogORM, "query", q):
        result = _observations("reports.cobranza_recurrente_rechazados", date(2026, 10, 13))
    assert len(result) == 1
    assert result[0]["observed_hour"] == "23:00"
    assert result[0]["observed_time"] == "23:25"
    assert "'cobranza_recurrente_rechazados'" in _where(q)
    assert "'reactivation_outcomes_daily'" not in _where(q)


def test_no_audit_is_not_failure(context):
    q = _query([])
    with patch.object(WarehouseAuditLogORM, "query", q):
        result = list_job_runs("reports.cobranza_recurrente_rechazados")
    assert result["coverage"] == "COMPLETION_MARKERS_ONLY"
    assert result["rows"] == []
    assert result["has_more"] is False


def test_naive_timestamps_are_not_assigned_a_timezone(context):
    q = _query([_row(datetime(2026, 10, 13, 8, 20))])
    with patch.object(WarehouseAuditLogORM, "query", q):
        result = _observations("reports.cobranza_recurrente_rechazados", date(2026, 10, 13))
    assert result == []
