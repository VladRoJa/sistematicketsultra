"""PostgreSQL 16 smoke for the incremental iVentas diagnosis migration.

Uses a synthetic isolated DB provided by GitHub Actions. Does NOT contact
iVentas or run app initialization, seed data, or production migrations.
"""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


def test_iventas_branch_failure_incremental_migration_postgresql_16():
    url = os.environ.get("IVENTAS_DIAG_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires explicit, synthetic CI PostgreSQL URL")

    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/f62a1b9d4c07_iventas_branch_failure_diagnostics.py"
    )
    spec = spec_from_file_location("iventas_branch_diag_pg16", path)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)

    assert module.revision == "f62a1b9d4c07"
    assert module.down_revision == "e856d3c21013"

    engine = sa.create_engine(url, future=True)
    try:
        with engine.begin() as connection:
            version = connection.exec_driver_sql("SHOW server_version_num").scalar()
            assert int(version) // 10000 == 16

            # Incremental fixture: prior Alembic history already owns parent
            # table; create only its required key in a fresh synthetic DB.
            connection.exec_driver_sql(
                "CREATE TABLE marketing_iventas_sync_runs (id BIGINT PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "INSERT INTO marketing_iventas_sync_runs (id) VALUES (132)"
            )

            module.op = Operations(MigrationContext.configure(connection))
            module.upgrade()
            assert (
                "marketing_iventas_branch_failures"
                in sa.inspect(connection).get_table_names()
            )

            insert = sa.text(
                "INSERT INTO marketing_iventas_branch_failures "
                "(sync_run_id, branch_code, error_type) "
                "VALUES (:run, :branch, :kind)"
            )
            connection.execute(insert, {
                "run": 132, "branch": "VILLA_VERDE", "kind": "IventasClientError",
            })
            observed = connection.exec_driver_sql(
                "SELECT sync_run_id, branch_code, error_type "
                "FROM marketing_iventas_branch_failures"
            ).one()
            assert tuple(observed) == (132, "VILLA_VERDE", "IventasClientError")

            bad_cases = (
                {"run": 132, "branch": "VILLA_VERDE", "kind": "IventasClientError"},
                {"run": 132, "branch": "OTRA", "kind": "RAW_SECRET_OR_TRACE"},
                {"run": 999, "branch": "OTRA", "kind": "IventasClientError"},
                {"run": 132, "branch": " " * 3, "kind": "IventasClientError"},
            )
            for case in bad_cases:
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(insert, case)

            with pytest.raises(RuntimeError, match="autorización explícita"):
                module.downgrade()

            connection.exec_driver_sql(
                "DELETE FROM marketing_iventas_branch_failures"
            )
            module.downgrade()
            assert (
                "marketing_iventas_branch_failures"
                not in sa.inspect(connection).get_table_names()
            )
    finally:
        engine.dispose()
