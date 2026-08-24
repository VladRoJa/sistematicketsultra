from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.warehouse.scheduler import (
    track_scheduler_worker as worker,
)


TIJUANA = ZoneInfo("America/Tijuana")


def test_retention_runs_at_configured_time(
    monkeypatch,
):
    monkeypatch.delenv(
        "WAREHOUSE_RETENTION_HOUR",
        raising=False,
    )
    monkeypatch.delenv(
        "WAREHOUSE_RETENTION_MINUTE",
        raising=False,
    )

    now_local = datetime(
        2026,
        8,
        25,
        1,
        10,
        tzinfo=TIJUANA,
    )

    assert worker._should_run_warehouse_retention(
        now_local=now_local,
        last_run_date=None,
    )


def test_retention_does_not_repeat_same_day():
    now_local = datetime(
        2026,
        8,
        25,
        1,
        10,
        tzinfo=TIJUANA,
    )

    assert not worker._should_run_warehouse_retention(
        now_local=now_local,
        last_run_date=date(2026, 8, 25),
    )


def test_retention_does_not_run_outside_window():
    now_local = datetime(
        2026,
        8,
        25,
        1,
        11,
        tzinfo=TIJUANA,
    )

    assert not worker._should_run_warehouse_retention(
        now_local=now_local,
        last_run_date=None,
    )
