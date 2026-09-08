from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.warehouse.scheduler import reports_scheduler_worker as worker


TIJUANA = ZoneInfo("America/Tijuana")


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    worker._COMPLETED_BY_JOB_AND_DATE.clear()
    worker._NEXT_RETRY_BY_JOB_AND_DATE.clear()
    yield
    worker._COMPLETED_BY_JOB_AND_DATE.clear()
    worker._NEXT_RETRY_BY_JOB_AND_DATE.clear()


def test_reactivation_sources_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REACTIVATION_SOURCES_ENABLED", raising=False)
    calls = {"job": 0}

    def fake_job(**_kwargs):
        calls["job"] += 1
        raise AssertionError("El job no debia ejecutarse.")

    monkeypatch.setattr(worker, "run_reactivation_sources_daily_job", fake_job)
    now = datetime(2026, 9, 8, 9, 5, tzinfo=TIJUANA)
    worker._run_reactivation_sources_if_due(now)
    assert calls["job"] == 0


def test_reactivation_sources_waits_when_track_priority_blocks(monkeypatch):
    monkeypatch.setattr(worker, "_should_run_daily_job", lambda **_kwargs: True)
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda _now: "track_reserved_window",
    )
    calls = {"job": 0}

    def fake_job(**_kwargs):
        calls["job"] += 1
        raise AssertionError("El job no debia ejecutarse.")

    monkeypatch.setattr(worker, "run_reactivation_sources_daily_job", fake_job)
    now = datetime(2026, 9, 8, 9, 5, tzinfo=TIJUANA)
    worker._run_reactivation_sources_if_due(now)
    assert calls["job"] == 0
    assert not worker._COMPLETED_BY_JOB_AND_DATE


def test_reactivation_sources_runs_and_persists_completion(monkeypatch):
    monkeypatch.setattr(worker, "_should_run_daily_job", lambda **_kwargs: True)
    monkeypatch.setattr(worker, "get_secondary_job_block_reason", lambda _now: None)
    monkeypatch.setattr(
        worker,
        "_find_persisted_scheduler_job_completion",
        lambda **_kwargs: None,
    )

    persisted = []

    def fake_persist(*, job_key, business_date):
        persisted.append((job_key, business_date))
        return 555

    monkeypatch.setattr(worker, "_persist_scheduler_job_completion", fake_persist)

    calls = []

    def fake_job(*, business_date, requested_by):
        calls.append((business_date, requested_by))
        return {
            "status": "completed",
            "business_date": business_date.isoformat(),
            "socios_activos_business_date": business_date.isoformat(),
            "socios_vencidos_business_date": "2026-09-07",
            "socios_activos": {"snapshot_id": 3},
            "socios_vencidos": {"snapshot_id": 86},
        }

    monkeypatch.setattr(worker, "run_reactivation_sources_daily_job", fake_job)

    now = datetime(2026, 9, 8, 9, 5, tzinfo=TIJUANA)
    worker._run_reactivation_sources_if_due(now)

    assert calls == [(now.date(), "reports_scheduler")]
    assert persisted == [("reactivation_sources_daily", now.date())]
    assert (
        "reactivation_sources_daily",
        now.date(),
    ) in worker._COMPLETED_BY_JOB_AND_DATE


def test_reactivation_sources_skips_persisted_completion(monkeypatch):
    monkeypatch.setattr(worker, "_should_run_daily_job", lambda **_kwargs: True)
    monkeypatch.setattr(worker, "get_secondary_job_block_reason", lambda _now: None)

    class ExistingCompletion:
        id = 777

    monkeypatch.setattr(
        worker,
        "_find_persisted_scheduler_job_completion",
        lambda **_kwargs: ExistingCompletion(),
    )

    calls = {"job": 0}

    def fake_job(**_kwargs):
        calls["job"] += 1
        raise AssertionError("No debia volver a ejecutar las fuentes.")

    monkeypatch.setattr(worker, "run_reactivation_sources_daily_job", fake_job)

    now = datetime(2026, 9, 8, 12, 0, tzinfo=TIJUANA)
    worker._run_reactivation_sources_if_due(now)

    assert calls["job"] == 0
    assert (
        "reactivation_sources_daily",
        now.date(),
    ) in worker._COMPLETED_BY_JOB_AND_DATE


def test_reactivation_sources_failure_schedules_retry(monkeypatch):
    monkeypatch.setattr(worker, "_should_run_daily_job", lambda **_kwargs: True)
    monkeypatch.setattr(worker, "get_secondary_job_block_reason", lambda _now: None)
    monkeypatch.setattr(
        worker,
        "_find_persisted_scheduler_job_completion",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        worker,
        "run_reactivation_sources_daily_job",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("fallo controlado")),
    )

    now = datetime(2026, 9, 8, 9, 5, tzinfo=TIJUANA)
    worker._run_reactivation_sources_if_due(now)

    retry_at = worker._NEXT_RETRY_BY_JOB_AND_DATE[
        ("reactivation_sources_daily", now.date())
    ]
    assert retry_at > now
    assert (
        "reactivation_sources_daily",
        now.date(),
    ) not in worker._COMPLETED_BY_JOB_AND_DATE
