from datetime import datetime

import pytest

from app.warehouse.scheduler import (
    track_scheduler_worker as worker,
)


def test_agregadoras_export_check_runs_every_five_minutes_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv(
        "AGREGADORAS_EXPORT_CHECK_MINUTE_STEP",
        raising=False,
    )

    eligible = datetime(
        2026,
        9,
        29,
        16,
        15,
        tzinfo=worker.TRACK_TIMEZONE,
    )
    not_eligible = datetime(
        2026,
        9,
        29,
        16,
        16,
        tzinfo=worker.TRACK_TIMEZONE,
    )

    assert (
        worker._agregadoras_export_check_key(eligible)
        == "2026-09-29T16:15"
    )
    assert (
        worker._agregadoras_export_check_key(not_eligible)
        is None
    )


def test_agregadoras_export_check_respects_configured_step(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "AGREGADORAS_EXPORT_CHECK_MINUTE_STEP",
        "10",
    )

    assert worker._agregadoras_export_check_key(
        datetime(
            2026,
            9,
            29,
            16,
            20,
            tzinfo=worker.TRACK_TIMEZONE,
        )
    ) == "2026-09-29T16:20"

    assert worker._agregadoras_export_check_key(
        datetime(
            2026,
            9,
            29,
            16,
            25,
            tzinfo=worker.TRACK_TIMEZONE,
        )
    ) is None


def test_agregadoras_export_check_invalid_step_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "AGREGADORAS_EXPORT_CHECK_MINUTE_STEP",
        "not-a-number",
    )

    assert worker._agregadoras_export_check_key(
        datetime(
            2026,
            9,
            29,
            16,
            30,
            tzinfo=worker.TRACK_TIMEZONE,
        )
    ) == "2026-09-29T16:30"
