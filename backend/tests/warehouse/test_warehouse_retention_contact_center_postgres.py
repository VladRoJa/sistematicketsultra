"""PostgreSQL 16 integration contract for Venta Total retention and Contact Center.

This test uses a dedicated, disposable localhost CI database only.
It never connects to or modifies a production database.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.warehouse.services import warehouse_retention_service as retention


@pytest.fixture
def isolated_postgres():
    raw_url = os.getenv("WAREHOUSE_RETENTION_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("Dedicated PostgreSQL CI database is not configured.")

    url = make_url(raw_url)
    if (
        url.database != "warehouse_retention_ci"
        or url.host not in ("127.0.0.1", "localhost")
        or not url.drivername.startswith("postgresql")
    ):
        pytest.fail("Refusing non-isolated PostgreSQL connection.")

    engine = create_engine(raw_url, pool_pre_ping=True)
    drop_sql = (
        "DROP TABLE IF EXISTS public.contact_center_appointment_result_events CASCADE",
        "DROP TABLE IF EXISTS public.contact_center_appointments CASCADE",
        "DROP TABLE IF EXISTS public.venta_total_snapshot_rows CASCADE",
        "DROP TABLE IF EXISTS public.venta_total_snapshots CASCADE",
    )
    try:
        with engine.begin() as connection:
            for statement in drop_sql:
                connection.execute(text(statement))
            connection.execute(text("""
                CREATE TABLE public.venta_total_snapshots (
                  id integer PRIMARY KEY,
                  business_date date NOT NULL,
                  is_canonical boolean NOT NULL DEFAULT false
                )
            """))
            connection.execute(text("""
                CREATE TABLE public.venta_total_snapshot_rows (
                  id integer PRIMARY KEY,
                  snapshot_id integer NOT NULL
                    REFERENCES public.venta_total_snapshots(id) ON DELETE CASCADE
                )
            """))
            connection.execute(text("""
                CREATE TABLE public.contact_center_appointments (
                  id integer PRIMARY KEY,
                  venta_total_snapshot_id integer
                    REFERENCES public.venta_total_snapshots(id) ON DELETE SET NULL,
                  venta_total_snapshot_row_id integer
                    REFERENCES public.venta_total_snapshot_rows(id) ON DELETE SET NULL
                )
            """))
            connection.execute(text("""
                CREATE TABLE public.contact_center_appointment_result_events (
                  id integer PRIMARY KEY,
                  venta_total_snapshot_id integer
                    REFERENCES public.venta_total_snapshots(id) ON DELETE SET NULL,
                  venta_total_snapshot_row_id integer
                    REFERENCES public.venta_total_snapshot_rows(id) ON DELETE SET NULL
                )
            """))
        yield engine
    finally:
        with engine.begin() as connection:
            for statement in drop_sql:
                connection.execute(text(statement))
        engine.dispose()


def test_retention_preserves_four_contact_center_reference_paths(
    monkeypatch, isolated_postgres
):
    engine = isolated_postgres
    today = datetime.now(ZoneInfo("America/Tijuana")).date()
    old = date(2020, 1, 1)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO public.venta_total_snapshots
                    (id, business_date, is_canonical)
                VALUES
                    (1, :old, true),
                    (2, :old, false),
                    (3, :old, false),
                    (4, :old, false),
                    (5, :old, false),
                    (6, :old, false),
                    (7, :today, false),
                    (8, :old, false)
            """),
            {"old": old, "today": today},
        )
        conn.execute(
            text("""
                INSERT INTO public.venta_total_snapshot_rows (id, snapshot_id)
                VALUES (101,1),(102,2),(103,3),(104,4),
                       (105,5),(106,6),(107,7),(108,8)
            """)
        )
        conn.execute(text("""
            INSERT INTO public.contact_center_appointments
                (id, venta_total_snapshot_id, venta_total_snapshot_row_id)
            VALUES (1, 2, NULL), (2, NULL, 103)
        """))
        conn.execute(text("""
            INSERT INTO public.contact_center_appointment_result_events
                (id, venta_total_snapshot_id, venta_total_snapshot_row_id)
            VALUES (1, 4, NULL), (2, NULL, 105)
        """))

    with Session(engine) as session:
        monkeypatch.setattr(retention, "db", SimpleNamespace(session=session))

        preview = retention.purge_venta_total_non_canonical_snapshots(
            retention_days=7, dry_run=True,
        )
        assert preview["target_snapshots"] == 2
        assert preview["target_rows"] == 2
        assert preview["deleted_snapshots"] == 0

        result = retention.purge_venta_total_non_canonical_snapshots(
            retention_days=7, batch_limit=1, max_batches=5,
        )
        assert result["deleted_snapshots"] == 2
        assert result["deleted_rows"] == 2

    with engine.connect() as conn:
        remaining = [
            row[0] for row in conn.execute(
                text("SELECT id FROM public.venta_total_snapshots ORDER BY id")
            )
        ]
        assert remaining == [1, 2, 3, 4, 5, 7]
        remaining_rows = [
            row[0] for row in conn.execute(
                text("SELECT id FROM public.venta_total_snapshot_rows ORDER BY id")
            )
        ]
        assert remaining_rows == [101, 102, 103, 104, 105, 107]
        appointments = conn.execute(text("""
            SELECT id, venta_total_snapshot_id, venta_total_snapshot_row_id
            FROM public.contact_center_appointments ORDER BY id
        """)).all()
        events = conn.execute(text("""
            SELECT id, venta_total_snapshot_id, venta_total_snapshot_row_id
            FROM public.contact_center_appointment_result_events ORDER BY id
        """)).all()
        assert [tuple(row) for row in appointments] == [
            (1, 2, None), (2, None, 103),
        ]
        assert [tuple(row) for row in events] == [
            (1, 4, None), (2, None, 105),
        ]


def test_concurrent_contact_center_verification_cannot_lose_evidence(
    monkeypatch, isolated_postgres,
):
    """Reproduce a late verification while retention waits for the parent row.

    The verifying transaction locks the snapshot first. Retention starts while
    no reference is committed, then waits on that lock. A reference is created
    and committed *before* retention can delete. The evidence must survive.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    engine = isolated_postgres
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO public.venta_total_snapshots
                (id, business_date, is_canonical)
            VALUES (201, :old, false)
        """), {"old": date(2020, 1, 1)})
        conn.execute(text("""
            INSERT INTO public.venta_total_snapshot_rows (id, snapshot_id)
            VALUES (301, 201)
        """))

    ready = Event()
    backend_pid = []
    def run_retention():
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '8s'"))
            backend_pid.append(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
            monkeypatch.setattr(retention, "db", SimpleNamespace(session=session))
            ready.set()
            return retention.purge_venta_total_non_canonical_snapshots(
                retention_days=7, batch_limit=1, max_batches=1,
            )

    with Session(engine) as verifying:
        # Hold the parent lock, then insert the verification within this same
        # transaction after the retention DELETE is already waiting for it.
        verifying.execute(text("""
            SELECT id FROM public.venta_total_snapshots
            WHERE id = 201 FOR UPDATE
        """)).one()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_retention)
            try:
                assert ready.wait(5), "Retention thread did not initialize."
                deadline = time.monotonic() + 5
                blocked = False
                while time.monotonic() < deadline:
                    with engine.connect() as observer:
                        wait = observer.execute(text("""
                            SELECT wait_event_type
                            FROM pg_stat_activity WHERE pid = :pid
                        """), {"pid": backend_pid[0]}).scalar_one_or_none()
                    if wait == "Lock":
                        blocked = True
                        break
                    if future.done():
                        break
                    time.sleep(0.05)
                assert blocked, "Retention never waited on snapshot lock."
                verifying.execute(text("""
                    INSERT INTO public.contact_center_appointments (
                        id, venta_total_snapshot_id, venta_total_snapshot_row_id
                    ) VALUES (10, 201, 301)
                """))
                verifying.commit()
                result = future.result(timeout=12)
            finally:
                if verifying.in_transaction():
                    verifying.rollback()

    with engine.connect() as conn:
        snapshot = conn.execute(text("""
            SELECT id FROM public.venta_total_snapshots WHERE id = 201
        """)).scalar_one_or_none()
        ref = conn.execute(text("""
            SELECT venta_total_snapshot_id, venta_total_snapshot_row_id
            FROM public.contact_center_appointments WHERE id = 10
        """)).one()
    assert result["deleted_snapshots"] == 0, (
        "Retention deleted evidence committed while it waited for a row lock."
    )
    assert snapshot == 201
    assert tuple(ref) == (201, 301)
