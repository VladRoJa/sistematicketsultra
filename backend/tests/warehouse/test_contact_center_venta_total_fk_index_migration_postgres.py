"""PostgreSQL 16 contract for the four Contact Center FK indexes.

Runs on a strictly named disposable local database, never production.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def isolated_postgres():
    raw_url = os.getenv("WAREHOUSE_RETENTION_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("Dedicated PostgreSQL CI database not configured.")
    url = make_url(raw_url)
    if (
        url.database != "warehouse_retention_ci"
        or url.host not in ("localhost", "127.0.0.1")
        or not url.drivername.startswith("postgresql")
    ):
        pytest.fail("Refusing non-isolated PostgreSQL connection.")

    engine = create_engine(raw_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                DROP TABLE IF EXISTS public.contact_center_appointment_result_events
                CASCADE
            """))
            connection.execute(text("""
                DROP TABLE IF EXISTS public.contact_center_appointments CASCADE
            """))
            connection.execute(text("""
                CREATE TABLE public.contact_center_appointments (
                  id integer PRIMARY KEY,
                  venta_total_snapshot_id integer,
                  venta_total_snapshot_row_id integer
                )
            """))
            connection.execute(text("""
                CREATE TABLE public.contact_center_appointment_result_events (
                  id integer PRIMARY KEY,
                  venta_total_snapshot_id integer,
                  venta_total_snapshot_row_id integer
                )
            """))
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("""
                DROP TABLE IF EXISTS public.contact_center_appointment_result_events
                CASCADE
            """))
            connection.execute(text("""
                DROP TABLE IF EXISTS public.contact_center_appointments CASCADE
            """))
        engine.dispose()


def test_migration_creates_and_drops_partial_indexes_concurrently(isolated_postgres):
    file = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "c21c10202601_contact_center_venta_total_fk_indexes.py"
    )
    spec = importlib.util.spec_from_file_location("cc_retention_index_migration", file)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "b20c10202601"
    expected = {entry[0]: entry[2] for entry in migration._INDEXES}

    with isolated_postgres.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            with context.begin_transaction():
                migration.upgrade()

        indexes = connection.execute(text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = ANY(:names)
        """), {"names": list(expected)}).all()
        assert {name for name, _definition in indexes} == set(expected)
        for name, definition in indexes:
            assert expected[name] in definition
            assert "IS NOT NULL" in definition

        connection.commit()  # End the metadata SELECT transaction before DDL.
        with Operations.context(context):
            with context.begin_transaction():
                migration.downgrade()
        remaining = connection.execute(text("""
            SELECT count(*) FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = ANY(:names)
        """), {"names": list(expected)}).scalar_one()
        assert remaining == 0
