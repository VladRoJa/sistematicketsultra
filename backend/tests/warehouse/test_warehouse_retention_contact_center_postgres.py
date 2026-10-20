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
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE INDEX ix_venta_total_snapshots_business_date
                ON public.venta_total_snapshots (business_date)
            """))
            connection.execute(text("""
                CREATE INDEX ix_venta_total_snapshots_is_canonical
                ON public.venta_total_snapshots (is_canonical)
            """))
            connection.execute(text("""
                CREATE INDEX ix_venta_total_snapshot_rows_snapshot_id
                ON public.venta_total_snapshot_rows (snapshot_id)
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



@pytest.mark.parametrize("reference_kind", ["snapshot", "row"])
def test_concurrent_contact_center_verification_cannot_lose_evidence(
    monkeypatch, isolated_postgres, reference_kind,
):
    """Preserve evidence when verification commits during retention selection.

    Explicitly hold either the parent snapshot row or a child Venta Total row,
    then start retention while that FK target is locked. With SKIP LOCKED,
    retention may complete without waiting. Both valid outcomes must preserve
    the subsequently committed reference.
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
            backend_pid.append(
                session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            )
            monkeypatch.setattr(retention, "db", SimpleNamespace(session=session))
            ready.set()
            return retention.purge_venta_total_non_canonical_snapshots(
                retention_days=7, batch_limit=1, max_batches=1,
            )

    with Session(engine) as verifying:
        if reference_kind == "snapshot":
            verifying.execute(text("""
                SELECT id FROM public.venta_total_snapshots
                WHERE id = 201 FOR UPDATE
            """)).one()
            ref_snapshot, ref_row = 201, None
        else:
            verifying.execute(text("""
                SELECT id FROM public.venta_total_snapshot_rows
                WHERE id = 301 FOR UPDATE
            """)).one()
            ref_snapshot, ref_row = None, 301

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_retention)
            try:
                assert ready.wait(5), "Retention thread did not initialize."
                deadline = time.monotonic() + 5
                attempted = False
                while time.monotonic() < deadline:
                    if future.done():
                        attempted = True
                        break
                    with engine.connect() as observer:
                        wait = observer.execute(text("""
                            SELECT wait_event_type
                            FROM pg_stat_activity WHERE pid = :pid
                        """), {"pid": backend_pid[0]}).scalar_one_or_none()
                    if wait == "Lock":
                        attempted = True
                        break
                    time.sleep(0.05)
                assert attempted, "Retention did not complete or wait on lock."
                verifying.execute(text("""
                    INSERT INTO public.contact_center_appointments (
                        id, venta_total_snapshot_id, venta_total_snapshot_row_id
                    ) VALUES (10, :snapshot_id, :row_id)
                """), {"snapshot_id": ref_snapshot, "row_id": ref_row})
                verifying.commit()
                result = future.result(timeout=12)
            finally:
                if verifying.in_transaction():
                    verifying.rollback()

    with engine.connect() as conn:
        snapshot = conn.execute(text("""
            SELECT id FROM public.venta_total_snapshots WHERE id = 201
        """)).scalar_one_or_none()
        row = conn.execute(text("""
            SELECT id FROM public.venta_total_snapshot_rows WHERE id = 301
        """)).scalar_one_or_none()
        ref = conn.execute(text("""
            SELECT venta_total_snapshot_id, venta_total_snapshot_row_id
            FROM public.contact_center_appointments WHERE id = 10
        """)).one()
    assert result["deleted_snapshots"] == 0, (
        "Retention deleted a snapshot with a concurrent committed verification."
    )
    assert snapshot == 201
    assert row == 301
    assert tuple(ref) == (ref_snapshot, ref_row)


def test_retention_batched_volume_and_evidence(monkeypatch, isolated_postgres):
    """Volume smoke test on synthetic schema with production's existing indexes.

    220 old snapshots, 8,800 line items, 30,000 Contact Center records.
    Protect four snapshots through each of the four evidence reference paths.
    Track elapsed seconds without a brittle runner-speed assertion.
    """
    from time import perf_counter

    engine = isolated_postgres
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO public.venta_total_snapshots (id, business_date, is_canonical)
            SELECT gs, :old, false FROM generate_series(1000, 1219) gs
        """), {"old": date(2020, 1, 1)})
        conn.execute(text("""
            INSERT INTO public.venta_total_snapshot_rows (id, snapshot_id)
            SELECT s.id * 100 + n, s.id
            FROM public.venta_total_snapshots s
            CROSS JOIN generate_series(1, 40) n
        """))
        conn.execute(text("""
            INSERT INTO public.contact_center_appointments
                (id, venta_total_snapshot_id, venta_total_snapshot_row_id)
            SELECT gs, 999 + gs, NULL FROM generate_series(1, 4) gs
        """))
        conn.execute(text("""
            INSERT INTO public.contact_center_appointments
                (id, venta_total_snapshot_id, venta_total_snapshot_row_id)
            SELECT gs + 4, NULL, (1003 + gs) * 100 + 1
            FROM generate_series(1, 4) gs
        """))
        conn.execute(text("""
            INSERT INTO public.contact_center_appointment_result_events
                (id, venta_total_snapshot_id, venta_total_snapshot_row_id)
            SELECT gs, 1007 + gs, NULL FROM generate_series(1, 4) gs
        """))
        conn.execute(text("""
            INSERT INTO public.contact_center_appointment_result_events
                (id, venta_total_snapshot_id, venta_total_snapshot_row_id)
            SELECT gs + 4, NULL, (1011 + gs) * 100 + 1
            FROM generate_series(1, 4) gs
        """))
        conn.execute(text("""
            INSERT INTO public.contact_center_appointments
                (id, venta_total_snapshot_id, venta_total_snapshot_row_id)
            SELECT 100000 + gs, NULL, NULL
            FROM generate_series(1, 15000) gs
        """))
        conn.execute(text("""
            INSERT INTO public.contact_center_appointment_result_events
                (id, venta_total_snapshot_id, venta_total_snapshot_row_id)
            SELECT 100000 + gs, NULL, NULL
            FROM generate_series(1, 15000) gs
        """))
        conn.execute(text("ANALYZE public.venta_total_snapshots"))
        conn.execute(text("ANALYZE public.venta_total_snapshot_rows"))
        conn.execute(text("ANALYZE public.contact_center_appointments"))
        conn.execute(text("ANALYZE public.contact_center_appointment_result_events"))

    with Session(engine) as session:
        monkeypatch.setattr(retention, "db", SimpleNamespace(session=session))
        start = perf_counter()
        preview = retention.purge_venta_total_non_canonical_snapshots(
            retention_days=7, dry_run=True,
        )
        preview_seconds = perf_counter() - start
        assert preview["target_snapshots"] == 204
        assert preview["target_rows"] == 8160

        start = perf_counter()
        result = retention.purge_venta_total_non_canonical_snapshots(
            retention_days=7, batch_limit=100, max_batches=10,
        )
        purge_seconds = perf_counter() - start
        assert result["deleted_snapshots"] == 204
        assert result["deleted_rows"] == 8160
        assert result["batches"] == 3

    with engine.connect() as conn:
        remaining_ids = [
            row[0] for row in conn.execute(text("""
                SELECT id FROM public.venta_total_snapshots ORDER BY id
            """))
        ]
        assert remaining_ids == list(range(1000, 1016))
        remaining_rows = conn.execute(
            text("SELECT COUNT(*) FROM public.venta_total_snapshot_rows")
        ).scalar_one()
        assert remaining_rows == 640
        assert conn.execute(text("""
            SELECT COUNT(*) FROM public.contact_center_appointments
            WHERE venta_total_snapshot_id IS NOT NULL
               OR venta_total_snapshot_row_id IS NOT NULL
        """)).scalar_one() == 8
        assert conn.execute(text("""
            SELECT COUNT(*) FROM public.contact_center_appointment_result_events
            WHERE venta_total_snapshot_id IS NOT NULL
               OR venta_total_snapshot_row_id IS NOT NULL
        """)).scalar_one() == 8

    print(
        "RETENTION_VOLUME_SMOKE "
        "snapshots=220 rows=8800 contact_center_records=30016 "
        f"preview_seconds={preview_seconds:.3f} "
        f"purge_seconds={purge_seconds:.3f} "
        f"batches={result['batches']}"
    )
