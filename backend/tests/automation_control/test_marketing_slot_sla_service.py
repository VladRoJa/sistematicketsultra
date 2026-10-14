"""M1-F4: SLA per scheduled Marketing sync slot, never five-source Funnel SLA."""
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import importlib.util
import os

import pytest

from app.services.automation_control.marketing_slot_sla_service import (
    marketing_slot_window, read_marketing_sync_sla,
)

TZ = ZoneInfo("America/Tijuana")
D = date(2026, 10, 14)
JOBS = ("marketing.iventas_sync", "marketing.meta_sync")


def _schedules(slots=("08:20", "12:20", "16:20", "20:20")):
    return {"jobs": [
        {"job_key": key, "state": "REPORTED", "schedule": {
            "enabled": True, "timezone": TZ.key, "kind": "DAILY_SLOTS",
            "slots": list(slots),
        }}
        for key in JOBS
    ]}


def _query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = rows
    return q


@pytest.mark.parametrize(("clock", "expected"), [
    ("2026-10-14T09:19:59-07:00", "NOT_DUE"),
    ("2026-10-14T09:20:00-07:00", "LAGGING"),
    ("2026-10-14T10:19:59-07:00", "LAGGING"),
    ("2026-10-14T10:20:00-07:00", "LATE"),
])
def test_exact_sixty_and_one_twenty_minutes(clock, expected):
    at = datetime.fromisoformat("2026-10-14T08:20:00-07:00")
    result = marketing_slot_window(scheduled_at=at, now=datetime.fromisoformat(clock))
    assert result["phase_if_unavailable"] == expected
    assert result["due_at"] == "2026-10-14T09:20:00-07:00"
    assert result["late_at"] == "2026-10-14T10:20:00-07:00"


def test_dst_elapsed_minutes_are_real_utc_minutes():
    # 01:30 PDT at the fall-back boundary + 60 minutes is 01:30 PST.
    first = datetime(2026, 11, 1, 1, 30, tzinfo=TZ, fold=0)
    result = marketing_slot_window(
        scheduled_at=first, now=datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc),
    )
    assert result["due_at"] == "2026-11-01T01:30:00-08:00"
    assert result["late_at"] == "2026-11-01T02:30:00-08:00"


@pytest.mark.parametrize(("clock", "expected"), [
    ("2026-10-14T08:00:00-07:00", "NOT_DUE"),
    ("2026-10-14T09:20:00-07:00", "LAGGING"),
    ("2026-10-14T10:20:00-07:00", "LATE"),
    ("2026-10-14T13:20:00-07:00", "LAGGING"),
    ("2026-10-14T14:20:00-07:00", "LATE"),
])
def test_slot_boundary_without_attributed_runs(clock, expected):
    with patch(
        "app.services.automation_control.marketing_slot_sla_service.read_effective_schedules",
        return_value=_schedules(),
    ), patch(
        "app.services.automation_control.marketing_slot_sla_service.db.session.query",
        side_effect=lambda *_: _query([]),
    ):
        value = read_marketing_sync_sla(
            business_date=D, now=datetime.fromisoformat(clock),
        )
    assert value["status"] == expected
    assert value["scope"] == "SYNC_ONLY_NOT_FUNNEL_CONSOLIDATED"


def test_both_canonical_completions_certify_only_sync_slot():
    at = datetime.fromisoformat("2026-10-14T08:20:00-07:00")
    finished = datetime.fromisoformat("2026-10-14T09:01:00-07:00")
    rows = [(1, "COMPLETED", True, finished)]
    with patch(
        "app.services.automation_control.marketing_slot_sla_service.read_effective_schedules",
        return_value=_schedules(),
    ), patch(
        "app.services.automation_control.marketing_slot_sla_service.db.session.query",
        side_effect=lambda *_: _query(rows),
    ):
        value = read_marketing_sync_sla(business_date=D, now=at.replace(hour=10,minute=21))
    assert value["status"] == "UP_TO_DATE"
    assert {s["status"] for s in value["sources"]} == {"UP_TO_DATE"}
    assert value["slot_at"] == at.isoformat()


def test_partial_or_failed_run_is_not_a_green():
    at = datetime.fromisoformat("2026-10-14T10:21:00-07:00")
    with patch(
        "app.services.automation_control.marketing_slot_sla_service.read_effective_schedules",
        return_value=_schedules(),
    ), patch(
        "app.services.automation_control.marketing_slot_sla_service.db.session.query",
        side_effect=[_query([(7, "PARTIAL", False, at)]),
                     _query([(8, "FAILED", False, at)])],
    ):
        value = read_marketing_sync_sla(business_date=D, now=at)
    assert value["status"] == "LATE"
    assert [x["status"] for x in value["sources"]] == ["LATE","LATE"]


def test_superseded_completion_unverified_not_false_red():
    at = datetime.fromisoformat("2026-10-14T10:21:00-07:00")
    with patch(
        "app.services.automation_control.marketing_slot_sla_service.read_effective_schedules",
        return_value=_schedules(),
    ), patch(
        "app.services.automation_control.marketing_slot_sla_service.db.session.query",
        side_effect=[_query([(7, "COMPLETED", False, at)]), _query([])],
    ):
        value = read_marketing_sync_sla(business_date=D, now=at)
    assert value["status"] == "UNKNOWN"


def test_historical_date_does_not_use_todays_effective_schedule():
    with patch(
        "app.services.automation_control.marketing_slot_sla_service.read_effective_schedules",
    ) as read:
        value = read_marketing_sync_sla(
            business_date=date(2026, 10, 13),
            now=datetime.fromisoformat("2026-10-14T12:00:00-07:00"),
        )
    read.assert_not_called()
    assert value["status"] == "UNKNOWN"


def test_unverified_or_divergent_schedule_does_not_query_run_tables():
    schedules = _schedules()
    schedules["jobs"][1]["schedule"]["slots"] = ["08:25"]
    with patch(
        "app.services.automation_control.marketing_slot_sla_service.read_effective_schedules",
        return_value=schedules,
    ), patch(
        "app.services.automation_control.marketing_slot_sla_service.db.session.query",
    ) as query:
        value = read_marketing_sync_sla(
            business_date=D, now=datetime.fromisoformat("2026-10-14T10:21:00-07:00"),
        )
    query.assert_not_called()
    assert value["status"] == "UNKNOWN"


def test_migration_ddl_is_nullable_and_revision_linear(monkeypatch):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from io import StringIO

    root = Path(__file__).resolve().parents[2] / "migrations"
    revision = ScriptDirectory(str(root)).get_revision("f856m1f40001")
    assert revision.down_revision == "f856opcap1013"
    stream = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql":True,"output_buffer":stream},
    )
    monkeypatch.setattr(revision.module, "op", Operations(ctx))
    revision.module.upgrade()
    ddl = stream.getvalue()
    assert ddl.count("ADD COLUMN scheduler_slot_at") == 2
    assert "NOT NULL" not in ddl.upper()
    assert "UPDATE " not in ddl.upper() and "DELETE " not in ddl.upper()


def test_postgres15_nullable_migration_preserves_legacy_runs(monkeypatch):
    raw = os.getenv("WORKER_HEARTBEAT_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Requires isolated ephemeral PostgreSQL 15 URL")
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    url = sa.engine.make_url(raw)
    if (url.get_backend_name() != "postgresql" or url.database != "heartbeat_ci"
            or url.username != "heartbeat_ci" or url.host not in ("localhost","127.0.0.1")):
        pytest.fail("Refusing non-synthetic database")
    root = Path(__file__).resolve().parents[2] / "migrations"
    revision = ScriptDirectory(str(root)).get_revision("f856m1f40001")
    engine = sa.create_engine(raw)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                conn.execute(sa.text("CREATE SCHEMA m1f4_slot_ci"))
                conn.execute(sa.text("SET LOCAL search_path TO m1f4_slot_ci"))
                schema = sa.MetaData()
                for table in ("marketing_iventas_sync_runs", "marketing_meta_sync_runs"):
                    sa.Table(table,schema,sa.Column("id",sa.BigInteger,primary_key=True))
                schema.create_all(conn)
                for table in ("marketing_iventas_sync_runs", "marketing_meta_sync_runs"):
                    conn.execute(sa.text(f"INSERT INTO {table}(id) VALUES (1)"))
                monkeypatch.setattr(revision.module,"op",Operations(MigrationContext.configure(conn)))
                revision.module.upgrade()
                for table in ("marketing_iventas_sync_runs", "marketing_meta_sync_runs"):
                    row = conn.execute(sa.text(
                        f"SELECT id, scheduler_slot_at FROM {table} WHERE id = 1"
                    )).one()
                    assert row == (1, None)
                    conn.execute(sa.text(
                        f"UPDATE {table} SET scheduler_slot_at = "
                        "'2026-10-14T08:20:00-07:00' WHERE id = 1"
                    ))
                    assert conn.scalar(sa.text(
                        f"SELECT scheduler_slot_at FROM {table} WHERE id = 1"
                    )) is not None
                revision.module.downgrade()
                for table in ("marketing_iventas_sync_runs", "marketing_meta_sync_runs"):
                    assert conn.scalar(sa.text(f"SELECT COUNT(*) FROM {table}")) == 1
            finally:
                tx.rollback()
    finally:
        engine.dispose()
