"""WSO-01 migration contract against a disposable PostgreSQL 16 database.

NEVER points at production. Requires localhost / database wso01_ci.
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import make_url

from migrations.versions import wso01caja110226_retire_corte_caja as migration


TABLES = (
    "corte_caja_snapshot_rows",
    "corte_caja_snapshots",
    "warehouse_audit_logs",
    "venta_total_snapshots",
    "planning_target_batches",
    "routine_control_provider_runs",
    "warehouse_uploads",
    "warehouse_report_types",
)

SCHEMA_SQL = (
    """CREATE TABLE public.warehouse_report_types (
      id integer PRIMARY KEY, key text NOT NULL UNIQUE)""",
    """CREATE TABLE public.warehouse_uploads (
      id integer PRIMARY KEY,
      report_type_id integer NOT NULL REFERENCES public.warehouse_report_types(id),
      stored_path text NOT NULL, stored_filename text NOT NULL)""",
    """CREATE TABLE public.warehouse_audit_logs (
      id integer PRIMARY KEY,
      upload_id integer REFERENCES public.warehouse_uploads(id))""",
    """CREATE TABLE public.corte_caja_snapshots (
      id integer PRIMARY KEY,
      warehouse_upload_id integer NOT NULL
        REFERENCES public.warehouse_uploads(id))""",
    """CREATE TABLE public.corte_caja_snapshot_rows (
      id integer PRIMARY KEY,
      snapshot_id integer NOT NULL
        REFERENCES public.corte_caja_snapshots(id) ON DELETE CASCADE)""",
    """CREATE TABLE public.venta_total_snapshots (
      id integer PRIMARY KEY,
      warehouse_upload_id integer NOT NULL
        REFERENCES public.warehouse_uploads(id) ON DELETE RESTRICT)""",
    """CREATE TABLE public.planning_target_batches (
      id integer PRIMARY KEY,
      source_upload_id integer REFERENCES public.warehouse_uploads(id)
        ON DELETE SET NULL)""",
    """CREATE TABLE public.routine_control_provider_runs (
      id integer PRIMARY KEY,
      raw_warehouse_upload_id integer REFERENCES public.warehouse_uploads(id)
        ON DELETE SET NULL)""",
)


@pytest.fixture
def pg():
    url = os.getenv("WSO01_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Dedicated synthetic PostgreSQL CI connection not configured")
    parsed = make_url(url)
    if (
        parsed.database != "wso01_ci"
        or parsed.host not in {"127.0.0.1", "localhost"}
        or not parsed.drivername.startswith("postgresql")
    ):
        pytest.fail("Refusing non-isolated PostgreSQL connection")

    engine = sa.create_engine(url)
    drop = [f"DROP TABLE IF EXISTS public.{table} CASCADE" for table in TABLES]
    try:
        with engine.begin() as conn:
            version = int(conn.exec_driver_sql("SHOW server_version_num").scalar()) // 10000
            assert version == 16
            for sql in drop:
                conn.exec_driver_sql(sql)
            for sql in SCHEMA_SQL:
                conn.exec_driver_sql(sql)

            conn.exec_driver_sql(
                "INSERT INTO public.warehouse_report_types VALUES "
                "(1,'corte_caja'), (2,'venta_total')"
            )
            conn.exec_driver_sql(
                "INSERT INTO public.warehouse_uploads VALUES "
                "(10,1,'uploads/warehouse/gasca/corte_caja/2026/09','corte.xlsx'),"
                "(20,2,'uploads/warehouse/gasca/venta_total/2026/09','venta.xlsx')"
            )
            conn.exec_driver_sql(
                "INSERT INTO public.corte_caja_snapshots VALUES (100,10)"
            )
            conn.exec_driver_sql(
                "INSERT INTO public.corte_caja_snapshot_rows VALUES (1000,100)"
            )
            conn.exec_driver_sql(
                "INSERT INTO public.warehouse_audit_logs VALUES (10000,10),(20000,20)"
            )
            conn.exec_driver_sql(
                "INSERT INTO public.venta_total_snapshots VALUES (200,20)"
            )
        yield engine
    finally:
        with engine.begin() as conn:
            for sql in drop:
                conn.exec_driver_sql(sql)
        engine.dispose()


def _apply(conn):
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        migration.upgrade()


def _count(conn, table):
    return conn.exec_driver_sql(f"SELECT COUNT(*) FROM public.{table}").scalar()


def test_retirement_deletes_only_corte_caja_and_preserves_venta_total(pg):
    with pg.begin() as conn:
        _apply(conn)
        assert not sa.inspect(conn).has_table("corte_caja_snapshots", schema="public")
        assert not sa.inspect(conn).has_table("corte_caja_snapshot_rows", schema="public")
        assert _count(conn, "warehouse_uploads") == 1
        assert _count(conn, "warehouse_audit_logs") == 1
        assert _count(conn, "venta_total_snapshots") == 1
        assert conn.exec_driver_sql(
            "SELECT key FROM public.warehouse_report_types"
        ).scalar() == "venta_total"


def test_nullable_fk_blocks_retirement_without_side_effects(pg):
    with pg.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO public.planning_target_batches VALUES (1,10)"
        )

    with pytest.raises(RuntimeError, match="live references"):
        with pg.begin() as conn:
            _apply(conn)

    with pg.connect() as conn:
        assert _count(conn, "warehouse_uploads") == 2
        assert _count(conn, "warehouse_audit_logs") == 2
        assert _count(conn, "corte_caja_snapshots") == 1
        assert _count(conn, "planning_target_batches") == 1


def test_shared_file_path_blocks_retirement(pg):
    with pg.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE public.warehouse_uploads "
            "SET stored_path='uploads/warehouse/gasca/corte_caja/2026/09', "
            "stored_filename='corte.xlsx' WHERE id=20"
        )

    with pytest.raises(RuntimeError, match="shared"):
        with pg.begin() as conn:
            _apply(conn)

    with pg.connect() as conn:
        assert _count(conn, "warehouse_uploads") == 2
        assert _count(conn, "corte_caja_snapshots") == 1
