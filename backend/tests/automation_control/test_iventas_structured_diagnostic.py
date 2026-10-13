from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.extensions import db
from app.models.marketing import MarketingIventasSyncRunORM, MarketingIventasBranchFailureORM
from app.services.automation_control.diagnostic_service import (
    run_diagnostic, last_error_diagnostic,
)


@pytest.fixture
def db_context():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def legacy_runs_have_no_branch_details(monkeypatch, db_context):
    query = MagicMock()
    query.filter_by.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.all.return_value = []
    monkeypatch.setattr(MarketingIventasBranchFailureORM, "query", query)


def _run(**overrides):
    values = dict(
        id=132,
        period_key="IVENTAS-2026-09",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 18),
        started_at=datetime(2026, 9, 18, 16, 20, 38, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 18, 16, 43, 13, tzinfo=timezone.utc),
        status="PARTIAL",
        branches_requested=26,
        branches_completed=24,
        branches_failed=2,
        aliases_unresolved=1,
        contacts_received=500,
    )
    values.update(overrides)
    return MarketingIventasSyncRunORM(**values)


def _query(row):
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = row
    return query


def test_partial_iventas_run_returns_exact_persisted_safe_counters(db_context):
    query = _query(_run())
    with patch.object(MarketingIventasSyncRunORM, "query", query):
        result = run_diagnostic("marketing.iventas_sync", 132)
    assert result["run_id"] == 132
    assert result["status"] == "PARTIAL"
    assert result["diagnostic_state"] == "STRUCTURED_COUNTERS_ONLY"
    assert result["source"] == "IVENTAS_RUN_COUNTERS"
    assert result["counts"] == {
        "branches_requested": 26,
        "branches_completed": 24,
        "branches_failed": 2,
        "aliases_unresolved": 1,
    }
    assert "24 de 26" in result["sanitized_message"]
    assert "2 no se completaron" in result["sanitized_message"]
    assert result["error_code"] is None
    assert result["log_state"] == "LOG_NOT_AVAILABLE"
    assert result["log_lines"] == []
    assert "causa técnica individual" in result["sanitized_message"].lower()
    query.filter.assert_called_once()


def test_iventas_counts_do_not_invent_failed_branches(db_context):
    query = _query(_run(branches_completed=26, branches_failed=0,
                        aliases_unresolved=0, status="COMPLETED"))
    with patch.object(MarketingIventasSyncRunORM, "query", query):
        result = run_diagnostic("marketing.iventas_sync", 132)
    assert result["counts"]["branches_failed"] == 0
    assert result["diagnostic_state"] == "STRUCTURED_COUNTERS_ONLY"
    assert "no garantiza la frescura" in result["sanitized_message"]
    assert result["error_code"] is None


def test_iventas_last_error_preserves_counters_and_uncertain_recovery(db_context):
    query = _query(_run())
    with patch.object(MarketingIventasSyncRunORM, "query", query):
        result = last_error_diagnostic("marketing.iventas_sync",
                                       business_date=date(2026, 9, 18))
    assert result["run_id"] == 132
    assert result["counts"]["branches_requested"] == 26
    assert result["failure_recency"] == "HISTORICAL_OR_ACTIVE_UNVERIFIED"


def test_unknown_branch_identity_not_made_up(db_context):
    query = _query(_run(branches_completed=25, branches_failed=1,
                        aliases_unresolved=0))
    with patch.object(MarketingIventasSyncRunORM, "query", query):
        result = run_diagnostic("marketing.iventas_sync", 132)
    assert "branch_code" not in str(result)
    assert "failed_branches" not in str(result)
    assert result["counts"]["branches_failed"] == 1
