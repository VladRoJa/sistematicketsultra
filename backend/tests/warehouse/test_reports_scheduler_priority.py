from datetime import datetime
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


def test_cobranza_waits_when_track_priority_blocks(
    monkeypatch,
):
    calls = {"job": 0}

    monkeypatch.setattr(
        worker,
        "_should_run_daily_job",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda now: "track_reserved_window",
    )

    def fake_job(*, business_date):
        calls["job"] += 1
        raise AssertionError(
            "Cobranza no debía ejecutarse."
        )

    monkeypatch.setattr(
        worker,
        "run_cobranza_recurrente_job",
        fake_job,
    )

    now = datetime(
        2026,
        8,
        24,
        9,
        10,
        tzinfo=TIJUANA,
    )

    worker._run_cobranza_recurrente_if_due(
        now
    )

    assert calls["job"] == 0
    assert not worker._COMPLETED_BY_JOB_AND_DATE


def test_cobranza_runs_when_track_priority_allows(
    monkeypatch,
):
    calls = {"job": 0}

    monkeypatch.setattr(
        worker,
        "_should_run_daily_job",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        worker,
        "get_secondary_job_block_reason",
        lambda now: None,
    )

    def fake_job(*, business_date):
        calls["job"] += 1

        return {
            "total_rows": 176,
            "total_files": 24,
            "duration_seconds": 48.4,
            "warehouse_publication": {
                "total_uploads": 25,
                "total_internal_documents": 24,
            },
        }

    monkeypatch.setattr(
        worker,
        "run_cobranza_recurrente_job",
        fake_job,
    )

    now = datetime(
        2026,
        8,
        24,
        8,
        40,
        tzinfo=TIJUANA,
    )

    worker._run_cobranza_recurrente_if_due(
        now
    )

    assert calls["job"] == 1

    assert (
        "cobranza_recurrente_rechazados",
        now.date(),
    ) in worker._COMPLETED_BY_JOB_AND_DATE
