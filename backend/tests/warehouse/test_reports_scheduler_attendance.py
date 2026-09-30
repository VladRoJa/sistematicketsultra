from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.warehouse.scheduler import (
    reports_scheduler_worker as worker,
)


TIJUANA = ZoneInfo("America/Tijuana")


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    worker._COMPLETED_BY_JOB_AND_DATE.clear()
    worker._NEXT_RETRY_BY_JOB_AND_DATE.clear()
    yield
    worker._COMPLETED_BY_JOB_AND_DATE.clear()
    worker._NEXT_RETRY_BY_JOB_AND_DATE.clear()


def _enable_attendance(monkeypatch):
    monkeypatch.setenv(
        "ATTENDANCE_DAILY_CAPTURE_ENABLED",
        "true",
    )


def test_attendance_capture_disabled_by_default(
    monkeypatch,
):
    monkeypatch.delenv(
        "ATTENDANCE_DAILY_CAPTURE_ENABLED",
        raising=False,
    )
    calls = {"job": 0}

    def fake_job(**_kwargs):
        calls["job"] += 1

    monkeypatch.setattr(
        worker,
        "run_attendance_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        30,
        6,
        25,
        tzinfo=TIJUANA,
    )

    worker._run_attendance_daily_capture_if_due(
        now
    )

    assert calls["job"] == 0


def test_attendance_capture_waits_until_scheduled_time(
    monkeypatch,
):
    _enable_attendance(monkeypatch)
    calls = {"job": 0}

    def fake_job(**_kwargs):
        calls["job"] += 1

    monkeypatch.setattr(
        worker,
        "run_attendance_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        30,
        6,
        19,
        tzinfo=TIJUANA,
    )

    worker._run_attendance_daily_capture_if_due(
        now
    )

    assert calls["job"] == 0


def test_attendance_capture_runs_for_previous_day(
    monkeypatch,
):
    _enable_attendance(monkeypatch)
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda _now: None,
    )
    monkeypatch.setattr(
        worker,
        "_find_existing_attendance_scheduler_success",
        lambda **_kwargs: None,
    )

    calls = []

    def fake_job(*, business_date):
        calls.append(business_date)
        return {
            "status": "SUCCESS",
            "run_id": 901,
            "business_date": (
                business_date.isoformat()
            ),
            "source_rows": 15000,
            "inserted_rows": 15000,
            "updated_rows": 0,
            "rejected_rows": 0,
        }

    monkeypatch.setattr(
        worker,
        "run_attendance_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        30,
        6,
        20,
        tzinfo=TIJUANA,
    )
    expected_date = (
        now.date() - timedelta(days=1)
    )

    worker._run_attendance_daily_capture_if_due(
        now
    )

    assert calls == [expected_date]
    assert (
        "attendance_daily_capture",
        expected_date,
    ) in worker._COMPLETED_BY_JOB_AND_DATE


def test_attendance_capture_skips_existing_scheduler_success(
    monkeypatch,
):
    _enable_attendance(monkeypatch)
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda _now: None,
    )
    monkeypatch.setattr(
        worker,
        "_find_existing_attendance_scheduler_success",
        lambda **_kwargs: SimpleNamespace(id=777),
    )

    calls = {"job": 0}

    def fake_job(**_kwargs):
        calls["job"] += 1
        raise AssertionError(
            "No debía volver a descargar asistencia."
        )

    monkeypatch.setattr(
        worker,
        "run_attendance_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        30,
        6,
        25,
        tzinfo=TIJUANA,
    )
    expected_date = (
        now.date() - timedelta(days=1)
    )

    worker._run_attendance_daily_capture_if_due(
        now
    )

    assert calls["job"] == 0
    assert (
        "attendance_daily_capture",
        expected_date,
    ) in worker._COMPLETED_BY_JOB_AND_DATE


def test_attendance_capture_failure_schedules_retry(
    monkeypatch,
):
    _enable_attendance(monkeypatch)
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda _now: None,
    )
    monkeypatch.setattr(
        worker,
        "_find_existing_attendance_scheduler_success",
        lambda **_kwargs: None,
    )
    def fake_job(**_kwargs):
        raise RuntimeError(
            "fallo controlado"
        )

    monkeypatch.setattr(
        worker,
        "run_attendance_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        30,
        6,
        25,
        tzinfo=TIJUANA,
    )
    expected_date = (
        now.date() - timedelta(days=1)
    )

    worker._run_attendance_daily_capture_if_due(
        now
    )

    retry_at = (
        worker._NEXT_RETRY_BY_JOB_AND_DATE[
            (
                "attendance_daily_capture",
                expected_date,
            )
        ]
    )

    assert retry_at > now
    assert (
        "attendance_daily_capture",
        expected_date,
    ) not in worker._COMPLETED_BY_JOB_AND_DATE


def test_attendance_capture_waits_when_track_blocks(
    monkeypatch,
):
    _enable_attendance(monkeypatch)
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda _now: "track_active",
    )

    calls = {"job": 0}

    def fake_job(**_kwargs):
        calls["job"] += 1

    monkeypatch.setattr(
        worker,
        "run_attendance_daily_capture_job",
        fake_job,
    )

    now = datetime(
        2026,
        9,
        30,
        6,
        25,
        tzinfo=TIJUANA,
    )

    worker._run_attendance_daily_capture_if_due(
        now
    )

    assert calls["job"] == 0
