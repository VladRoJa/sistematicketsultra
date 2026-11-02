"""WSO-02 pruning contract with a disposable localhost PostgreSQL database."""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import make_url
from alembic.migration import MigrationContext
from alembic.operations import Operations

from scripts.ops import wso02_iventas_payload_prune as prune
from migrations.versions import wso02ivnt110226_mark_pruned_iventas_run_payload as migration


TABLES = (
    "marketing_iventas_contact_tags",
    "marketing_iventas_raw_pages",
    "contact_center_contact_links",
    "marketing_reactivation_campaigns",
    "marketing_campaign_v2_campaigns",
    "marketing_iventas_contacts",
    "marketing_iventas_sync_runs",
)


@pytest.fixture
def pg():
    url = os.getenv("WSO02_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("WSO02_TEST_POSTGRES_URL not configured")
    parsed = make_url(url)
    if (
        parsed.drivername != "postgresql+psycopg2"
        or parsed.host not in {"127.0.0.1", "localhost"}
        or parsed.database != "wso02_ci"
    ):
        pytest.fail("Refusing to run test against a non-synthetic database")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as c:
            assert int(c.exec_driver_sql("SHOW server_version_num").scalar_one()) // 10000 == 16
            for table in TABLES:
                c.exec_driver_sql(f"DROP TABLE IF EXISTS public.{table} CASCADE")
            c.exec_driver_sql("""
                CREATE TABLE public.marketing_iventas_sync_runs (
                    id bigint PRIMARY KEY,
                    period_key text NOT NULL,
                    date_from date NOT NULL,
                    date_to date NOT NULL,
                    status text NOT NULL,
                    is_canonical boolean NOT NULL DEFAULT false,
                    contacts_unique bigint NOT NULL DEFAULT 0,
                    payload_pruned_at timestamptz NULL
                )
            """)
            c.exec_driver_sql("""
                CREATE TABLE public.marketing_iventas_contacts (
                    id bigint PRIMARY KEY,
                    sync_run_id bigint NOT NULL REFERENCES
                      public.marketing_iventas_sync_runs(id) ON DELETE CASCADE
                )
            """)
            c.exec_driver_sql("""
                CREATE TABLE public.marketing_iventas_contact_tags (
                    id bigint PRIMARY KEY,
                    sync_run_id bigint NOT NULL,
                    iventas_contact_row_id bigint NOT NULL
                      REFERENCES public.marketing_iventas_contacts(id) ON DELETE CASCADE
                )
            """)
            c.exec_driver_sql("""
                CREATE TABLE public.marketing_iventas_raw_pages (
                    id bigint PRIMARY KEY,
                    sync_run_id bigint NOT NULL REFERENCES
                      public.marketing_iventas_sync_runs(id) ON DELETE CASCADE
                )
            """)
            c.exec_driver_sql("""
                CREATE TABLE public.contact_center_contact_links (
                    id bigint PRIMARY KEY,
                    source_type text NOT NULL,
                    source_row_id bigint NULL
                )
            """)
            c.exec_driver_sql("""
                CREATE TABLE public.marketing_reactivation_campaigns (
                    id bigint PRIMARY KEY, filters_json json NOT NULL
                )
            """)
            c.exec_driver_sql("""
                CREATE TABLE public.marketing_campaign_v2_campaigns (
                    id bigint PRIMARY KEY, audience_definition_json json NOT NULL
                )
            """)
            c.exec_driver_sql("""
                INSERT INTO public.marketing_iventas_sync_runs
                 (id, period_key, date_from, date_to, status, is_canonical, contacts_unique)
                VALUES
                 (1, 'IVENTAS-2026-10', '2026-10-01', '2026-10-31', 'COMPLETED', false, 2),
                 (2, 'IVENTAS-2026-10', '2026-10-01', '2026-10-31', 'COMPLETED', true, 1),
                 (3, 'IVENTAS-2026-10', '2026-10-01', '2026-10-30', 'COMPLETED', false, 1),
                 (4, 'IVENTAS-2026-10', '2026-10-01', '2026-10-30', 'COMPLETED', false, 1),
                 (5, 'IVENTAS-2026-09', '2026-09-01', '2026-09-30', 'PARTIAL', false, 1),
                 (6, 'IVENTAS-2026-08', '2026-08-01', '2026-08-31', 'COMPLETED', false, 1),
                 (7, 'IVENTAS-2026-08', '2026-08-01', '2026-08-31', 'COMPLETED', true, 1),
                 (8, 'IVENTAS-2026-07', '2026-07-01', '2026-07-31', 'COMPLETED', false, 1),
                 (9, 'IVENTAS-2026-07', '2026-07-01', '2026-07-31', 'COMPLETED', true, 1)
            """)
            c.exec_driver_sql("""
                INSERT INTO public.marketing_iventas_contacts (id, sync_run_id)
                VALUES (101,1),(102,1),(201,2),(301,3),(401,4),(501,5),
                       (601,6),(701,7),(801,8),(901,9)
            """)
            c.exec_driver_sql("""
                INSERT INTO public.marketing_iventas_contact_tags
                VALUES (1,1,101),(2,2,201),(3,3,301)
            """)
            c.exec_driver_sql("""
                INSERT INTO public.marketing_iventas_raw_pages
                VALUES (1,1),(2,2),(3,3),(4,4),(5,5)
            """)
            c.exec_driver_sql("""
                INSERT INTO public.contact_center_contact_links
                VALUES (1,'IVENTAS_CONTACT',301)
            """)
            c.exec_driver_sql("""
                INSERT INTO public.marketing_reactivation_campaigns
                VALUES (1, '{"sources":{"iventas_sync_run_id":6}}')
            """)
            c.exec_driver_sql("""
                INSERT INTO public.marketing_campaign_v2_campaigns
                VALUES (1, '{"source_metadata":{"iventas_sync_run_id":8}}')
            """)
        yield engine
    finally:
        with engine.begin() as c:
            for table in TABLES:
                c.exec_driver_sql(f"DROP TABLE IF EXISTS public.{table} CASCADE")
        engine.dispose()


def test_preview_only_superseded_completed_without_cc_links(pg):
    with pg.connect() as conn:
        rows = prune._manifest_rows(conn)
    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert (rows[0]["contact_rows"], rows[0]["tag_rows"], rows[0]["raw_pages"]) == (2, 1, 1)


def test_prune_one_is_scoped_preserves_run_and_restarts_idempotently(pg):
    with pg.connect() as conn:
        item = prune._manifest_rows(conn)[0]

    with pg.begin() as conn:
        assert prune._prune_one(conn, item) == "pruned"

    with pg.connect() as conn:
        assert prune._counts(conn, 1) == {
            "tag_rows": 0, "contact_rows": 0, "raw_pages": 0
        }
        assert conn.execute(text("""
            SELECT contacts_unique FROM public.marketing_iventas_sync_runs
            WHERE id = 1 AND payload_pruned_at IS NOT NULL
        """)).scalar_one() == 2
        assert prune._counts(conn, 2) == {
            "tag_rows": 1, "contact_rows": 1, "raw_pages": 1
        }
        assert prune._counts(conn, 3)["contact_rows"] == 1
        assert prune._counts(conn, 5)["contact_rows"] == 1

    with pg.begin() as conn:
        assert prune._prune_one(conn, item) == "already_pruned"


def test_manifest_mismatch_rolls_back_before_any_child_deletion(pg):
    with pg.connect() as conn:
        item = prune._manifest_rows(conn)[0]
    item["tag_rows"] += 1
    with pytest.raises(RuntimeError, match="tag_rows changed"):
        with pg.begin() as conn:
            prune._prune_one(conn, item)
    with pg.connect() as conn:
        assert prune._counts(conn, 1)["contact_rows"] == 2
        assert prune._counts(conn, 1)["tag_rows"] == 1
        assert conn.execute(text("""
            SELECT payload_pruned_at FROM public.marketing_iventas_sync_runs WHERE id=1
        """)).scalar_one() is None


@pytest.mark.parametrize("run_id", [2, 3, 4, 5, 6, 7, 8, 9])
def test_canonical_cc_campaign_pinned_latest_and_partial_are_blocked(pg, run_id):
    with pg.connect() as conn:
        row = conn.execute(text("""
            SELECT period_key, date_from, date_to
            FROM public.marketing_iventas_sync_runs WHERE id=:id
        """), {"id": run_id}).mappings().one()
        counts = prune._counts(conn, run_id)
    item = {
        "id": run_id, "period_key": row["period_key"],
        "date_from": row["date_from"].isoformat(),
        "date_to": row["date_to"].isoformat(), **counts
    }
    with pytest.raises(RuntimeError, match="no longer eligible"):
        with pg.begin() as conn:
            prune._prune_one(conn, item)
    with pg.connect() as conn:
        assert prune._counts(conn, run_id)["contact_rows"] == 1


def test_migration_adds_marker_and_downgrade_refuses_data_loss(pg):
    with pg.begin() as conn:
        conn.exec_driver_sql("""
            ALTER TABLE public.marketing_iventas_sync_runs
            DROP COLUMN payload_pruned_at
        """)
    with pg.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert "payload_pruned_at" in {
            c["name"] for c in sa.inspect(conn).get_columns(
                "marketing_iventas_sync_runs", schema="public"
            )
        }
        conn.exec_driver_sql("""
            UPDATE public.marketing_iventas_sync_runs
            SET payload_pruned_at = now() WHERE id = 1
        """)

    with pytest.raises(RuntimeError, match="downgrade blocked"):
        with pg.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()


def test_bounded_batches_resume_without_reprocessing_prior_runs(monkeypatch, tmp_path):
    from contextlib import contextmanager
    from types import SimpleNamespace

    class Engine:
        @contextmanager
        def begin(self):
            yield object()

    states = {1: False, 2: False, 3: False}
    seen = []

    def fake_prune(_conn, item):
        run_id = item["id"]
        seen.append(run_id)
        if states[run_id]:
            return "already_pruned"
        states[run_id] = True
        return "pruned"

    monkeypatch.setattr(prune, "_prune_one", fake_prune)
    monkeypatch.setattr(
        prune.shutil, "disk_usage",
        lambda _path: SimpleNamespace(free=50 * 1024 ** 3),
    )
    items = [{"id": i} for i in (1, 2, 3)]
    results = [
        prune._apply_items(
            engine=Engine(), items=items,
            manifest_parent=tmp_path, max_runs=1, min_free_gb=30,
        )
        for _ in range(3)
    ]
    assert [r["runs_pruned"] for r in results] == [1, 1, 1]
    assert [r["runs_remaining_in_manifest"] for r in results] == [2, 1, 0]
    assert states == {1: True, 2: True, 3: True}
    assert seen == [1, 1, 2, 1, 2, 3]
