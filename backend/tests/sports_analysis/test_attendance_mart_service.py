from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.sports_analysis.attendance_mart_service import (
    _build_intervals,
)


def _visit(
    entered_hour: int,
    entered_minute: int,
    exited_hour: int,
    exited_minute: int,
):
    return SimpleNamespace(
        entered_at_utc=datetime(
            2026,
            6,
            18,
            entered_hour,
            entered_minute,
            tzinfo=timezone.utc,
        ),
        exited_at_utc=datetime(
            2026,
            6,
            18,
            exited_hour,
            exited_minute,
            tzinfo=timezone.utc,
        ),
        visit_status="CLOSED",
        member_pin="00123",
    )


def test_exit_at_bucket_boundary_is_not_carried_forward():
    # Junio en Tijuana usa UTC-7:
    # 13:00 UTC -> 06:00 local
    # 13:15 UTC -> 06:15 local
    rows = _build_intervals(
        [_visit(13, 0, 13, 15)],
        business_date=date(2026, 6, 18),
    )

    at_0600 = rows[24]
    at_0615 = rows[25]

    assert at_0600["occupancy"] == 1
    assert at_0615["occupancy"] == 0


def test_entry_at_bucket_boundary_belongs_to_new_bucket():
    rows = _build_intervals(
        [_visit(13, 15, 13, 30)],
        business_date=date(2026, 6, 18),
    )

    at_0600 = rows[24]
    at_0615 = rows[25]

    assert at_0600["occupancy"] == 0
    assert at_0615["occupancy"] == 1
