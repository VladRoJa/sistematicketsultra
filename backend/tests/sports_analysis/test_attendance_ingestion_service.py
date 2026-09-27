from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.sports_analysis import attendance_ingestion_service
from app.sports_analysis.attendance_parser import (
    AttendanceParseResult,
    AttendanceVisitRecord,
)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, existing_rows):
        self.existing_rows = existing_rows
        self.added = []

    def query(self, *_args):
        return _FakeQuery(self.existing_rows)

    def add(self, row):
        self.added.append(row)


def _record(
    *,
    first_name: str,
    last_name: str,
) -> AttendanceVisitRecord:
    return AttendanceVisitRecord(
        business_date=date(2026, 6, 18),
        source_row_number=3,
        member_pin="00123",
        source_first_name=first_name,
        source_last_name=last_name,
        source_branch_name="SEND MXL",
        entered_at_utc=datetime(
            2026,
            6,
            18,
            13,
            0,
            tzinfo=timezone.utc,
        ),
        exited_at_utc=datetime(
            2026,
            6,
            18,
            14,
            0,
            tzinfo=timezone.utc,
        ),
        duration_seconds=3600,
        visit_status="CLOSED",
        age=29,
        age_is_valid=True,
        city="MEXICALI",
        postal_code="21000",
        member_since=date(2025, 1, 1),
        attendance_type="SOCIO",
        has_opening=False,
        source_fingerprint="stable-fingerprint",
    )


def test_existing_fingerprint_updates_names_without_insert(
    monkeypatch,
):
    existing = SimpleNamespace(
        source_fingerprint="stable-fingerprint",
        source_first_name=None,
        source_last_name=None,
    )
    fake_session = _FakeSession([existing])

    monkeypatch.setattr(
        attendance_ingestion_service,
        "db",
        SimpleNamespace(session=fake_session),
    )
    monkeypatch.setattr(
        attendance_ingestion_service,
        "_resolve_branch_cached",
        lambda *_args, **_kwargs: 5,
    )

    result = AttendanceParseResult(
        source_rows=1,
        visits=(
            _record(
                first_name="Ana Maria",
                last_name="Prueba Lopez",
            ),
        ),
        rejections=(),
    )

    inserted_rows, updated_rows = (
        attendance_ingestion_service._persist_visits(
            result,
            run_id=22,
        )
    )

    assert inserted_rows == 0
    assert updated_rows == 1
    assert fake_session.added == []
    assert existing.source_first_name == "Ana Maria"
    assert existing.source_last_name == "Prueba Lopez"
    assert existing.last_run_id == 22
