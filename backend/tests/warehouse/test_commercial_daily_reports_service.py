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
    assert monthly["K3"].value == 150  # September historical monthly close.
    assert monthly["L3"].value == 14  # October MTD at cutoff.
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
    assert report["Totales Mensuales"]["L3"].value == 7
