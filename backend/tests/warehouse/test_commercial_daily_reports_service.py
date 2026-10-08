from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.warehouse.services.commercial_daily_reports_service import (
    CommercialDailyReportError,
    _daily_deltas,
    _week_start,
    render_commercial_daily_xlsx,
)


def test_week_starts_on_sunday():
    assert _week_start(date(2026, 10, 7)) == date(2026, 10, 4)
    assert _week_start(date(2026, 10, 3)) == date(2026, 9, 27)
    assert _week_start(date(2026, 10, 4)) == date(2026, 10, 4)


def test_mtd_month_boundary():
    assert _daily_deltas({
        date(2026, 9, 29): 100,
        date(2026, 9, 30): 106,
        date(2026, 10, 1): 4,
        date(2026, 10, 2): 8,
    }) == {
        date(2026, 9, 29): None,
        date(2026, 9, 30): 6,
        date(2026, 10, 1): 4,
        date(2026, 10, 2): 4,
    }


def test_mtd_gap_not_interpreted_as_zero():
    result = _daily_deltas({
        date(2026, 10, 1): 5,
        date(2026, 10, 3): 9,
    })
    assert result[date(2026, 10, 3)] is None


def test_mtd_decrease_rejected():
    with pytest.raises(CommercialDailyReportError):
        _daily_deltas({
            date(2026, 10, 1): 8,
            date(2026, 10, 2): 5,
        })


def test_report_has_three_sheets_and_week_to_date_value():
    cutoff = date(2026, 10, 7)
    d = date(2026, 10, 1)
    series = {}
    for n in range(7):
        series[d.replace(day=n + 1)] = n + 1
    payload = render_commercial_daily_xlsx(
        metric="venta_nueva",
        cutoff=cutoff,
        mtd_series={"VILLA_VERDE": series},
    )
    wb = load_workbook(BytesIO(payload), data_only=True)
    assert wb.sheetnames == ["Diario", "Semanal", "Totales Mensuales"]
    assert wb["Diario"]["A3"].value == "VILLA_VERDE"
    assert wb["Diario"]["B3"].value == 1
    weekly = wb["Semanal"]
    assert weekly.cell(row=3, column=weekly.max_column).value == 4

def test_subtotals_and_region_summary_follow_catalog_metadata():
    cutoff = date(2026, 10, 7)
    days = [date(2026, 10, i) for i in range(1, 8)]
    data = {
        "VILLAS": {day: i for i, day in enumerate(days, 1)},
        "SERRANIA": {day: 2 * i for i, day in enumerate(days, 1)},
    }
    metadata = {
        "VILLAS": {
            "order": 1, "label": "VILLAS DEL REY",
            "group": "Subtotal 21 gyms", "region": "Mexicali"
        },
        "SERRANIA": {
            "order": 26, "label": "SERRANIA",
            "group": "Subtotal gyms nuevos", "region": "Costa"
        },
    }
    book = load_workbook(
        BytesIO(render_commercial_daily_xlsx(
            metric="reactivaciones",
            cutoff=cutoff,
            mtd_series=data,
            branch_metadata=metadata,
        )),
        data_only=True,
    )
    daily = book["Diario"]
    assert [daily[f"A{row}"].value for row in range(3, 8)] == [
        "VILLAS DEL REY", "Subtotal 21 gyms",
        "SERRANIA", "Subtotal gyms nuevos", "TOTAL",
    ]
    weekly = book["Semanal"]
    assert weekly["A9"].value == "REGIONES"
    assert weekly["A10"].value == "Costa"
    assert weekly["A11"].value == "Mexicali"
    last = weekly.max_column
    assert weekly.cell(row=7, column=last).value == 12
    assert weekly.cell(row=10, column=last).value == 8
    assert weekly.cell(row=11, column=last).value == 4


def test_reactivaciones_february_correction_does_not_fake_negative_daily():
    """Monthly historical snapshots stay readable despite old MTD corrections."""
    series = {
        date(2026, 2, 12): 33,
        date(2026, 2, 13): 31,  # A corrected cumulative total, not -2 visits.
        date(2026, 2, 28): 99,
        date(2026, 9, 30): 150,
        **{date(2026, 10, day): 2 * day for day in range(1, 8)},
    }
    payload = render_commercial_daily_xlsx(
        metric="reactivaciones",
        cutoff=date(2026, 10, 7),
        mtd_series={"VILLA_VERDE": series},
    )
    book = load_workbook(BytesIO(payload), data_only=True)
    weekly = book["Semanal"]
    daily = book["Diario"]
    monthly = book["Totales Mensuales"]

    assert book.sheetnames == ["Diario", "Semanal", "Totales Mensuales"]
    assert weekly.max_column == 2  # Only Sunday October 4 onwards; no false Jan-Sep weekly totals.
    assert weekly["B2"].value == "04/10-10/10 (corte 07/10)"
    assert weekly["B3"].value == 8
    assert daily["B3"].value == 2
    assert daily["E3"].value == 2
    assert daily["F3"].value is None  # Future day never counted as zero.
    assert monthly["C3"].value == 99  # February closing MTD, not daily net deltas.
    assert monthly["J3"].value == 150  # September historical monthly close.
    assert monthly["K3"].value == 14  # October MTD at cutoff.
    assert "04/10/2026" in daily["A1"].value
    assert "DESDE 04/10/2026" in weekly["A1"].value
    assert "07/10/2026" in monthly["A1"].value


def test_reactivaciones_current_period_correction_fails_closed():
    days = {
        date(2026, 10, 1): 11,
        date(2026, 10, 2): 8,
        date(2026, 10, 3): 15,
        date(2026, 10, 4): 18,
    }
    with pytest.raises(CommercialDailyReportError, match="2026-10-02"):
        render_commercial_daily_xlsx(
            metric="reactivaciones",
            cutoff=date(2026, 10, 4),
            mtd_series={"VILLA_VERDE": days},
        )


def test_reactivaciones_monthly_history_without_old_daily_dates():
    series = {
        date(2026, 1, 31): 80,
        date(2026, 2, 28): 90,
        date(2026, 10, 1): 3,
        date(2026, 10, 2): 4,
        date(2026, 10, 3): 6,
        date(2026, 10, 4): 7,
    }
    report = load_workbook(
        BytesIO(render_commercial_daily_xlsx(
            metric="reactivaciones",
            cutoff=date(2026, 10, 4),
            mtd_series={"VILLA_VERDE": series},
        )),
        data_only=True,
    )
    assert report["Semanal"]["B3"].value == 1
    assert report["Totales Mensuales"]["B3"].value == 80
    assert report["Totales Mensuales"]["C3"].value == 90
    assert report["Totales Mensuales"]["K3"].value == 7


def test_reactivaciones_ignores_retired_historical_club_but_requires_current_ones(monkeypatch):
    from types import SimpleNamespace
    from app.warehouse.services import commercial_daily_reports_service as service

    jan31 = date(2026, 1, 31)
    cutoff = date(2026, 10, 7)
    version_by_day = {
        jan31: SimpleNamespace(id=11, status="success"),
        cutoff: SimpleNamespace(id=27, status="success"),
    }
    monkeypatch.setattr(service, "_resolve_canonical_version", version_by_day.get)

    class FakeColumn:
        def in_(self, keys):
            return True

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows
        def filter(self, *args):
            return self
        def all(self):
            return self.rows

    rows = [
        SimpleNamespace(
            sucursal_canon="LA_VIGA", track_date=jan31,
            track_daily_version_id=11, reactivaciones_real_mtd=40,
        ),
        SimpleNamespace(
            sucursal_canon="VILLA_VERDE", track_date=jan31,
            track_daily_version_id=11, reactivaciones_real_mtd=30,
        ),
        SimpleNamespace(
            sucursal_canon="VILLA_VERDE", track_date=cutoff,
            track_daily_version_id=27, reactivaciones_real_mtd=15,
        ),
        SimpleNamespace(
            sucursal_canon="SERRANIA", track_date=cutoff,
            track_daily_version_id=27, reactivaciones_real_mtd=8,
        ),
    ]
    monkeypatch.setattr(
        service, "TrackDailyMartORM",
        SimpleNamespace(
            track_daily_version_id=FakeColumn(),
            query=FakeQuery(rows),
        ),
    )
    output = service._load_series(
        "reactivaciones",
        cutoff,
        active_branches={"VILLA_VERDE", "SERRANIA"},
    )
    assert set(output) == {"VILLA_VERDE", "SERRANIA"}
    assert output["VILLA_VERDE"][jan31] == 30
    assert output["SERRANIA"][cutoff] == 8

    with pytest.raises(CommercialDailyReportError, match="MISSING_CLUB"):
        service._load_series(
            "reactivaciones",
            cutoff,
            active_branches={"VILLA_VERDE", "SERRANIA", "MISSING_CLUB"},
        )


def test_jan_apr_reactivaciones_historical_baseline_has_all_branches():
    from app.warehouse.services.reactivaciones_monthly_baseline_service import (
        load_early_reactivaciones_monthly,
    )
    snapshot = load_early_reactivaciones_monthly()
    assert len(snapshot) == 26
    assert snapshot["VILLA_VERDE"][date(2026, 1, 1)] == 169
    for month, expected in (
        (1, 4311), (2, 2684), (3, 3789), (4, 2684)
    ):
        assert sum(
            values[date(2026, month, 1)]
            for values in snapshot.values()
        ) == expected


def test_jan_apr_reactivaciones_fills_only_missing_monthly_track_data():
    from app.warehouse.services.reactivaciones_monthly_baseline_service import (
        load_early_reactivaciones_monthly,
    )
    snapshot = load_early_reactivaciones_monthly()
    series = {
        branch: {
            date(2026, 5, 31): 27,
            **{date(2026, 10, day): day * 2 for day in range(1, 8)},
        }
        for branch in snapshot
    }
    payload = render_commercial_daily_xlsx(
        metric="reactivaciones",
        cutoff=date(2026, 10, 7),
        mtd_series=series,
        historical_monthly_by_branch=snapshot,
    )
    book = load_workbook(BytesIO(payload), data_only=True)
    monthly = book["Totales Mensuales"]
    total_row = next(
        row for row in range(3, monthly.max_row + 1)
        if monthly.cell(row, 1).value == "TOTAL"
    )
    assert [
        monthly.cell(total_row, col).value for col in range(2, 6)
    ] == [4311, 2684, 3789, 2684]
    assert monthly.cell(total_row, 6).value == 26 * 27
    assert monthly.cell(total_row, 11).value == 26 * 14


def test_jan_apr_reactivaciones_rejects_conflict_with_existing_canonical_close():
    from app.warehouse.services.reactivaciones_monthly_baseline_service import (
        load_early_reactivaciones_monthly,
    )
    snapshot = load_early_reactivaciones_monthly()
    series = {
        branch: {
            date(2026, 10, 1): 2,
            date(2026, 10, 2): 4,
            date(2026, 10, 3): 6,
            date(2026, 10, 4): 8,
        }
        for branch in snapshot
    }
    series["VILLA_VERDE"][date(2026, 1, 31)] = 170
    with pytest.raises(CommercialDailyReportError, match="Historical Reactivaciones conflict"):
        render_commercial_daily_xlsx(
            metric="reactivaciones",
            cutoff=date(2026, 10, 4),
            mtd_series=series,
            historical_monthly_by_branch=snapshot,
        )
