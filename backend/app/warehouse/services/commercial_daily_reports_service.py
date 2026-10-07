"""Deterministic daily/weekly/monthly commercial XLSX from canonical Track MTD."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO

import xlsxwriter

from app.models.warehouse import TrackDailyMartORM
from app.warehouse.services.track_daily_version_service import (
    get_current_track_daily_version,
)

METRICS = {
    "venta_nueva": ("clientes_nuevos_real_mtd", "VENTA NUEVA"),
    "reactivaciones": ("reactivaciones_real_mtd", "REACTIVACIONES"),
}
FIRST_SUPPORTED_DATE = date(2026, 1, 1)


class CommercialDailyReportError(RuntimeError):
    pass


def _week_start(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _daily_deltas(mtd_by_day: dict[date, int | None]) -> dict[date, int | None]:
    """No silently convert missing business dates to zero."""
    result: dict[date, int | None] = {}
    for day in sorted(mtd_by_day):
        current = mtd_by_day[day]
        if current is None:
            result[day] = None
            continue
        previous = day - timedelta(days=1)
        if day.day == 1:
            result[day] = current
        elif previous in mtd_by_day and mtd_by_day[previous] is not None:
            delta = current - mtd_by_day[previous]
            if delta < 0:
                raise CommercialDailyReportError(
                    f"MTD decreasing within month for {day.isoformat()}"
                )
            result[day] = delta
        else:
            result[day] = None
    return result


def _resolve_canonical_version(day: date):
    for version_type in ("cierre_canonico", "base_nocturna_canonica"):
        version = get_current_track_daily_version(
            track_date=day, version_type=version_type
        )
        if version is not None and version.status == "success":
            return version
    return None


def _load_series(metric: str, cutoff: date) -> dict[str, dict[date, int | None]]:
    field, _ = METRICS[metric]
    start = FIRST_SUPPORTED_DATE
    versions = {}
    day = start
    while day <= cutoff:
        version = _resolve_canonical_version(day)
        if version is not None:
            versions[day] = version.id
        day += timedelta(days=1)
    if cutoff not in versions:
        raise CommercialDailyReportError(
            f"Track closed base unavailable for {cutoff.isoformat()}"
        )
    if not versions:
        raise CommercialDailyReportError("No canonical Track versions")
    rows = (
        TrackDailyMartORM.query
        .filter(TrackDailyMartORM.track_daily_version_id.in_(versions.values()))
        .all()
    )
    by_branch: dict[str, dict[date, int | None]] = defaultdict(dict)
    for row in rows:
        branch = str(row.sucursal_canon)
        if row.track_date in versions and row.track_daily_version_id == versions[row.track_date]:
            by_branch[branch][row.track_date] = getattr(row, field)
    if not by_branch:
        raise CommercialDailyReportError("Track mart has no commercial rows")
    missing = [branch for branch, series in by_branch.items() if series.get(cutoff) is None]
    if missing:
        raise CommercialDailyReportError(
            f"Missing commercial MTD on cutoff {cutoff.isoformat()}: {missing}"
        )
    return dict(by_branch)


def _format_sheet(book, name, headers, branches, cells):
    sheet = book.add_worksheet(name)
    sheet.freeze_panes(2, 1)
    sheet.set_column(0, 0, 28)
    sheet.set_column(1, max(1, len(headers) - 1), 13)
    title = book.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#153E63", "font_size": 14})
    heading = book.add_format({"bold": True, "bg_color": "#D8E8F4", "border": 1})
    numeric = book.add_format({"num_format": "#,##0", "align": "center"})
    missing = book.add_format({"bg_color": "#FFF0CC", "align": "center"})
    sheet.merge_range(0, 0, 0, len(headers) - 1, name.upper(), title)
    for col, header in enumerate(headers):
        sheet.write(1, col, header, heading)
    for index, branch in enumerate(branches, 2):
        sheet.write(index, 0, branch)
        for col, value in enumerate(cells[branch], 1):
            if value is None:
                sheet.write_blank(index, col, None, missing)
            else:
                sheet.write_number(index, col, int(value), numeric)
    total_row = len(branches) + 2
    sheet.write(total_row, 0, "TOTAL", heading)
    for col in range(1, len(headers)):
        vals = [cells[branch][col - 1] for branch in branches]
        if any(v is None for v in vals):
            sheet.write_blank(total_row, col, None, missing)
        else:
            sheet.write_number(total_row, col, sum(vals), heading)
    sheet.autofilter(1, 0, len(branches) + 1, len(headers) - 1)


def render_commercial_daily_xlsx(
    *, metric: str, cutoff: date, mtd_series: dict[str, dict[date, int | None]]
) -> bytes:
    """Pure rendering layer, with explicit gaps and Sunday-Saturday buckets."""
    if metric not in METRICS:
        raise ValueError(f"Unsupported report metric: {metric}")
    branches = sorted(mtd_series)
    if not branches:
        raise CommercialDailyReportError("No branches")

    daily = {b: _daily_deltas(mtd_series[b]) for b in branches}
    week = _week_start(cutoff)
    weeks = []
    cursor = _week_start(FIRST_SUPPORTED_DATE)
    while cursor <= week:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    months = []
    cursor = FIRST_SUPPORTED_DATE.replace(day=1)
    while cursor <= cutoff.replace(day=1):
        months.append(cursor)
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

    day_headers = [week + timedelta(days=n) for n in range(7)]
    daily_cells = {
        b: [daily[b].get(d) if d <= cutoff else None for d in day_headers]
        for b in branches
    }
    weekly_cells = {}
    monthly_cells = {}
    for b in branches:
        weekly_cells[b] = []
        for start in weeks:
            valid_days = [start + timedelta(days=i) for i in range(7)
                          if start + timedelta(days=i) <= cutoff]
            values = [daily[b].get(d) for d in valid_days]
            weekly_cells[b].append(
                sum(values) if valid_days and all(v is not None for v in values)
                else None
            )
        monthly_cells[b] = []
        for month in months:
            days = [d for d in mtd_series[b] if d.year == month.year and d.month == month.month and d <= cutoff]
            expected_day = cutoff if (month.year, month.month) == (cutoff.year, cutoff.month) else (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            monthly_cells[b].append(
                mtd_series[b].get(expected_day)
                if expected_day in days else None
            )

    stream = BytesIO()
    book = xlsxwriter.Workbook(stream, {"in_memory": True})
    book.set_properties({"title": f"Reporte {METRICS[metric][1]} {cutoff.isoformat()}"})
    _format_sheet(book, "Diario", ["Sucursal"] + [d.strftime("%d/%m/%Y") for d in day_headers], branches, daily_cells)
    _format_sheet(book, "Semanal", ["Sucursal"] + [f"{w:%d/%m}-{w + timedelta(days=6):%d/%m}" + (f" (corte {cutoff:%d/%m})" if w == week and cutoff < w + timedelta(days=6) else "") for w in weeks], branches, weekly_cells)
    _format_sheet(book, "Totales Mensuales", ["Sucursal"] + [m.strftime("%m/%Y") for m in months], branches, monthly_cells)
    book.close()
    return stream.getvalue()


def build_commercial_daily_xlsx(*, metric: str, cutoff: date) -> bytes:
    if metric not in METRICS:
        raise ValueError(metric)
    return render_commercial_daily_xlsx(
        metric=metric, cutoff=cutoff, mtd_series=_load_series(metric, cutoff)
    )
