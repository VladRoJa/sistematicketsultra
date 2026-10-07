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


def test_report_has_three_sheets_and_weekly_missing_not_zero():
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
    assert weekly.cell(row=3, column=weekly.max_column).value is None
