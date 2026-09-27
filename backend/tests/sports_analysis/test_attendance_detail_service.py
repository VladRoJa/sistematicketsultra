from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.sports_analysis import attendance_detail_service as detail
from app.sports_analysis.attendance_identity_service import (
    AttendanceIdentityResolution,
)


def _visit():
    return SimpleNamespace(
        id=101,
        business_date=date(2026, 9, 25),
        source_branch_name="SALTILLO VILLALTA",
        source_first_name="ANA",
        source_last_name="PRUEBA",
        member_pin="00123",
        entered_at_utc=datetime(
            2026,
            9,
            25,
            15,
            0,
            tzinfo=timezone.utc,
        ),
        exited_at_utc=datetime(
            2026,
            9,
            25,
            16,
            0,
            tzinfo=timezone.utc,
        ),
        visit_status="CLOSED",
        duration_seconds=3600,
        age=30,
        city="Saltillo",
        postal_code="25000",
        member_since=date(2025, 1, 1),
        attendance_type="SOCIO",
        has_opening=False,
    )


def test_visit_detail_uses_batch_identity_resolution(
    monkeypatch,
):
    visit = _visit()
    calls = []

    def _resolve(visits, *, session):
        calls.append(
            {
                "visits": visits,
                "session": session,
            }
        )
        return {
            101: AttendanceIdentityResolution(
                id_socio="331909",
                display_name="Ana Canonica",
                identity_method="EXACT_PIN_ALTA",
                source_snapshot_id=21,
            )
        }

    monkeypatch.setattr(
        detail,
        "resolve_attendance_identities",
        _resolve,
    )

    dataset = {
        "identity_enrichment": True,
        "serialize": detail._serialize_visit_row,
    }
    rows = [
        (visit, "Saltillo Sur"),
    ]

    serialized = detail._serialize_dataset_rows(
        dataset,
        rows,
    )

    assert len(calls) == 1
    assert calls[0]["visits"] == [visit]

    assert serialized == [
        {
            "business_date": "25/09/2026",
            "branch_name": "Saltillo Sur",
            "display_name": "Ana Canonica",
            "id_socio": "331909",
            "member_pin": "00123",
            "identity_method": "EXACT_PIN_ALTA",
            "identity_snapshot_id": 21,
            "entered_at": "25/09/2026 08:00:00",
            "exited_at": "25/09/2026 09:00:00",
            "visit_status": "CLOSED",
            "duration_minutes": 60.0,
            "age": 30,
            "city": "Saltillo",
            "postal_code": "25000",
            "member_since": "01/01/2025",
            "attendance_type": "SOCIO",
            "has_opening": "No",
            "source_branch_name": "SALTILLO VILLALTA",
        }
    ]


def test_visit_detail_identity_columns_are_not_sortable():
    columns = {
        column["key"]: column
        for column in detail._VISIT_COLUMNS
    }

    for key in (
        "display_name",
        "id_socio",
        "identity_method",
    ):
        assert columns[key]["sortable"] is False

    assert "member_pin" in detail._VISIT_SORTS
    assert "display_name" not in detail._VISIT_SORTS
    assert "id_socio" not in detail._VISIT_SORTS
    assert "identity_method" not in detail._VISIT_SORTS
