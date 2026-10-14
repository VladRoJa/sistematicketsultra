"""Migración Alembic y diagnóstico atribuido del error iVentas por sucursal."""
from datetime import date, datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.marketing import (
    MarketingIventasBranchFailureORM,
    MarketingIventasSyncRunORM,
)
from app.services.automation_control.diagnostic_service import run_diagnostic


def _migration():
    path = (Path(__file__).resolve().parents[2] / "migrations/versions"
            / "f62a1b9d4c07_iventas_branch_failure_diagnostics.py")
    spec = spec_from_file_location("iventas_branch_failure_migration_test", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db_ctx():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)
    with app.app_context():
        yield


def test_migration_sqlite_create_constraints_and_safe_downgrade():
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _migration()
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql(
            "CREATE TABLE marketing_iventas_sync_runs (id BIGINT PRIMARY KEY)"
        )
        conn.exec_driver_sql(
            "INSERT INTO marketing_iventas_sync_runs (id) VALUES (132)"
        )
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        cols = {x[1] for x in conn.exec_driver_sql(
            "PRAGMA table_info(marketing_iventas_branch_failures)"
        ).all()}
        assert cols == {"sync_run_id", "branch_code", "error_type", "created_at"}

        stmt = sa.text(
            "INSERT INTO marketing_iventas_branch_failures "
            "(sync_run_id,branch_code,error_type) VALUES (:id,:branch,:type)"
        )
        conn.execute(stmt, {"id":132,"branch":"VILLA_VERDE","type":"IventasClientError"})
        with pytest.raises(IntegrityError):
            conn.execute(stmt, {"id":132,"branch":"VILLA_VERDE","type":"IventasClientError"})
        with pytest.raises(IntegrityError):
            conn.execute(stmt, {"id":132,"branch":"OTRA","type":"Bearer SECRET_RAW"})
        with pytest.raises(IntegrityError):
            conn.execute(stmt, {"id":999,"branch":"OTRA","type":"IventasClientError"})
        with pytest.raises(RuntimeError, match="autorización explícita"):
            migration.downgrade()
        conn.exec_driver_sql("DELETE FROM marketing_iventas_branch_failures")
        migration.downgrade()
        assert not conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE name='marketing_iventas_branch_failures'"
        ).fetchall()
    engine.dispose()


def test_postgres_upgrade_sql_contains_fk_check_and_pk():
    migration = _migration()
    output = StringIO()
    migration.op = Operations(MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql":True,"output_buffer":output},
    ))
    migration.upgrade()
    sql = output.getvalue()
    assert "marketing_iventas_branch_failures" in sql
    assert "marketing_iventas_sync_runs" in sql
    assert "ON DELETE CASCADE" in sql
    assert "ALIAS_AMBIGUOUS_DESTINATION" in sql
    assert "PRIMARY KEY" in sql


def _run(status="PARTIAL"):
    return MarketingIventasSyncRunORM(
        id=132, period_key="2026-10", date_from=date(2026,10,1),
        date_to=date(2026,10,13), status=status,
        started_at=datetime(2026,10,13,15,tzinfo=timezone.utc),
        finished_at=datetime(2026,10,13,16,tzinfo=timezone.utc),
        branches_requested=26, branches_completed=25, branches_failed=1,
        aliases_unresolved=0,
    )


def _query(rows=None):
    query=MagicMock()
    for method in ("filter", "filter_by", "order_by", "limit"):
        getattr(query,method).return_value=query
    query.first.return_value=rows[0] if rows else None
    query.all.return_value=rows or []
    return query


def test_diagnostic_read_only_exact_run_safe_type(db_ctx):
    parent=_query([_run()])
    child=_query([
        SimpleNamespace(branch_code="VILLA_VERDE", error_type="IventasClientError"),
        SimpleNamespace(branch_code="OTHER", error_type="RAW_SECRETS_ARE_FORBIDDEN"),
    ])
    with (patch.object(MarketingIventasSyncRunORM,"query",parent),
          patch.object(MarketingIventasBranchFailureORM,"query",child)):
        result=run_diagnostic("marketing.iventas_sync",132)
    assert result["run_id"]==132
    assert result["branch_failures"]==[
        {"branch_code":"VILLA_VERDE","error_type":"IventasClientError"},
    ]
    assert result["failure_details_coverage"]=="RECORDED_ONLY"
    assert result["failure_details_truncated"] is False
    assert "RAW_SECRETS" not in str(result)
    child.filter_by.assert_called_once_with(sync_run_id=132)
    child.limit.assert_called_once_with(101)


def test_historical_partial_has_no_invented_branch_details(db_ctx):
    parent=_query([_run()])
    child=_query([])
    with (patch.object(MarketingIventasSyncRunORM,"query",parent),
          patch.object(MarketingIventasBranchFailureORM,"query",child)):
        result=run_diagnostic("marketing.iventas_sync",132)
    assert result["counts"]["branches_failed"] == 1
    assert result["branch_failures"] == []
    assert result["failure_details_coverage"] == "NOT_RECORDED"
    assert result["log_state"] == "LOG_NOT_AVAILABLE"


def test_completed_does_not_fetch_branch_errors(db_ctx):
    parent=_query([_run(status="COMPLETED")])
    child=_query([])
    with (patch.object(MarketingIventasSyncRunORM,"query",parent),
          patch.object(MarketingIventasBranchFailureORM,"query",child)):
        result=run_diagnostic("marketing.iventas_sync",132)
    assert "branch_failures" not in result
    child.filter_by.assert_not_called()
