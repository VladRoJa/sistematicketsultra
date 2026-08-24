from datetime import datetime
from zoneinfo import ZoneInfo

from app.warehouse.services import (
    scheduler_priority_service as service,
)


TIJUANA = ZoneInfo("America/Tijuana")


def _time(hour: int, minute: int) -> datetime:
    return datetime(
        2026,
        8,
        24,
        hour,
        minute,
        tzinfo=TIJUANA,
    )


def test_secondary_window_allows_expected_minutes():
    assert service.is_secondary_execution_window(
        _time(8, 20)
    )
    assert service.is_secondary_execution_window(
        _time(8, 40)
    )
    assert service.is_secondary_execution_window(
        _time(8, 44)
    )


def test_secondary_window_blocks_track_buffers():
    assert not service.is_secondary_execution_window(
        _time(8, 19)
    )
    assert not service.is_secondary_execution_window(
        _time(8, 45)
    )
    assert not service.is_secondary_execution_window(
        _time(8, 59)
    )


def test_secondary_window_blocks_overnight():
    assert not service.is_secondary_execution_window(
        _time(23, 20)
    )
    assert not service.is_secondary_execution_window(
        _time(4, 30)
    )


def test_block_reason_detects_active_track(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "has_active_track_work",
        lambda: True,
    )

    assert (
        service.get_secondary_job_block_reason(
            _time(8, 20)
        )
        == "track_active"
    )


def test_block_reason_allows_secondary_job(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "has_active_track_work",
        lambda: False,
    )

    assert (
        service.get_secondary_job_block_reason(
            _time(8, 20)
        )
        is None
    )
