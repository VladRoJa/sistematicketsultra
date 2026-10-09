"""Deterministic daily/weekly/monthly commercial XLSX from canonical Track MTD."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from io import BytesIO

from app.warehouse.services.reactivaciones_monthly_baseline_service import (
    load_early_reactivaciones_monthly,
)

import xlsxwriter

from app.models.warehouse import TrackDailyMartORM, TrackBranchCatalogORM
from app.models.suite_governance import SuiteSucursalRegionAssignmentORM
from app.warehouse.services.track_daily_version_service import (
    get_current_track_daily_version,
)

METRICS = {
    "venta_nueva": ("clientes_nuevos_real_mtd", "VENTA NUEVA"),
    "reactivaciones": ("reactivaciones_real_mtd", "REACTIVACIONES"),
}
FIRST_SUPPORTED_DATE = date(2026, 1, 1)
MONTH_NAMES_ES = (
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
)
# Until a complete validated daily archive is available, do not derive
# historical reactivations from corrected monthly cumulative snapshots.
# Reactivaciones weekly comparison always uses the last three calendar
# months, including the reporting month. Never fabricate historical days.


class CommercialDailyReportError(RuntimeError):
    pass


def _week_start(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _three_month_window_start(cutoff: date) -> date:
    """First day of the current month and the two preceding months."""
    month_number = cutoff.year * 12 + cutoff.month - 1 - 2
    start = date(month_number // 12, month_number % 12 + 1, 1)
    return max(start, FIRST_SUPPORTED_DATE)


def _daily_deltas(
    mtd_by_day: dict[date, int | None],
    *, historical_corrections_before: date | None = None,
) -> dict[date, int | None]:
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
                if (
                    historical_corrections_before is not None
                    and day < historical_corrections_before
                ):
                    # Older corrected MTD is not evidence of negative
                    # activity. Mark this day/its week unavailable.
                    result[day] = None
                    continue
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


def _load_series(
    metric: str,
    cutoff: date,
    *,
    active_branches: set[str] | None = None,
) -> dict[str, dict[date, int | None]]:
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
    if active_branches is not None:
        # Historical marts can contain retired clubs. Exclude them without
        # suppressing a genuinely missing current active-club cutoff.
        by_branch = {
            branch: series for branch, series in by_branch.items()
            if branch in active_branches
        }
        required = set(active_branches)
    else:
        required = set(by_branch)
    if not by_branch:
        raise CommercialDailyReportError("Track mart has no commercial rows")
    missing = [
        branch for branch in sorted(required)
        if by_branch.get(branch, {}).get(cutoff) is None
    ]
    if missing:
        raise CommercialDailyReportError(
            f"Missing commercial MTD on cutoff {cutoff.isoformat()}: {missing}"
        )
    return dict(by_branch)


def _load_branch_metadata() -> dict[str, dict]:
    """Use existing opening order and current Suite governance region."""
    metadata = {}
    for row in TrackBranchCatalogORM.query.filter_by(is_track_active=True).all():
        opening_order = getattr(getattr(row, "sucursal", None), "orden_apertura", None)
        group = None
        if opening_order is not None:
            group = "Subtotal 21 gyms" if opening_order <= 21 else "Subtotal gyms nuevos"
        metadata[row.sucursal_canon] = {
            "order": row.display_order,
            "label": row.track_label,
            "group": group,
            "region": None,
            "sucursal_id": row.sucursal_id,
        }
    region_assignments = (
        SuiteSucursalRegionAssignmentORM.query
        .filter_by(is_current=True)
        .all()
    )
    regions = {
        assignment.sucursal_id: assignment.region.region_label
        for assignment in region_assignments
        if assignment.region is not None and assignment.region.is_active
    }
    for data in metadata.values():
        data["region"] = regions.get(data["sucursal_id"])
    return metadata


def _format_sheet(
    book, name, headers, branches, cells,
    branch_metadata=None, title_text=None,
    center_summary_numbers=False, center_headers=False,
):
    sheet = book.add_worksheet(name)
    sheet.freeze_panes(2, 1)
    sheet.set_column(0, 0, 31)
    sheet.set_column(1, max(1, len(headers) - 1), 15)
    title = book.add_format({
        "bold": True, "font_color": "#FFFFFF",
        "bg_color": "#153E63", "font_size": 14, "shrink": True,
    })
    heading = book.add_format({
        "bold": True, "bg_color": "#D8E8F4", "border": 1
    })
    centered_heading = book.add_format({
        "bold": True, "bg_color": "#D8E8F4", "border": 1,
        "align": "center", "num_format": "#,##0",
    })
    summary_number = centered_heading if center_summary_numbers else heading
    numeric = book.add_format({"num_format": "#,##0", "align": "center"})
    missing = book.add_format({"bg_color": "#FFF0CC", "align": "center"})
    sheet.merge_range(0, 0, 0, len(headers) - 1, title_text or name.upper(), title)
    for col, header in enumerate(headers):
        sheet.write(
            1, col, header,
            centered_heading if center_headers and col > 0 else heading,
        )

    branch_metadata = branch_metadata or {}
    groups: list[tuple[str | None, list[str]]] = []
    if any(branch_metadata.get(b, {}).get("group") for b in branches):
        for group_title in ("Subtotal 21 gyms", "Subtotal gyms nuevos"):
            members = [
                b for b in branches
                if branch_metadata.get(b, {}).get("group") == group_title
            ]
            if members:
                groups.append((group_title, members))
        other = [
            b for b in branches
            if branch_metadata.get(b, {}).get("group") not in {
                "Subtotal 21 gyms", "Subtotal gyms nuevos"
            }
        ]
        if other:
            groups.append(("Subtotal sin clasificar", other))
    else:
        groups = [(None, branches)]

    current_row = 2
    for group_title, members in groups:
        for branch in members:
            sheet.write(
                current_row, 0,
                branch_metadata.get(branch, {}).get("label") or branch
            )
            for col, value in enumerate(cells[branch], 1):
                if value is None:
                    sheet.write_blank(current_row, col, None, missing)
                else:
                    sheet.write_number(current_row, col, int(value), numeric)
            current_row += 1
        if group_title:
            sheet.write(current_row, 0, group_title, heading)
            for col in range(1, len(headers)):
                vals = [cells[b][col - 1] for b in members]
                if any(v is None for v in vals):
                    sheet.write_blank(current_row, col, None, missing)
                else:
                    sheet.write_number(current_row, col, sum(vals), summary_number)
            current_row += 1

    sheet.write(current_row, 0, "TOTAL", heading)
    for col in range(1, len(headers)):
        vals = [cells[branch][col - 1] for branch in branches]
        if any(v is None for v in vals):
            sheet.write_blank(current_row, col, None, missing)
        else:
            sheet.write_number(current_row, col, sum(vals), summary_number)

    if name == "Semanal":
        by_region: dict[str, list[str]] = defaultdict(list)
        for branch in branches:
            region = branch_metadata.get(branch, {}).get("region")
            if region:
                by_region[region].append(branch)
        if by_region:
            current_row += 2
            sheet.write(current_row, 0, "REGIONES", heading)
            current_row += 1
            for region in sorted(by_region):
                sheet.write(current_row, 0, region, heading)
                for col in range(1, len(headers)):
                    vals = [cells[b][col - 1] for b in by_region[region]]
                    if any(v is None for v in vals):
                        sheet.write_blank(current_row, col, None, missing)
                    else:
                        sheet.write_number(current_row, col, sum(vals), numeric)
                current_row += 1




def render_commercial_daily_xlsx(
    *, metric: str, cutoff: date, mtd_series: dict[str, dict[date, int | None]],
    branch_metadata: dict[str, dict] | None = None,
    historical_monthly_by_branch: dict[str, dict[date, int]] | None = None,
) -> bytes:
    """Pure rendering layer, with explicit gaps and Sunday-Saturday buckets."""
    if metric not in METRICS:
        raise ValueError(f"Unsupported report metric: {metric}")
    branch_metadata = branch_metadata or {}
    branches = sorted(
        mtd_series,
        key=lambda b: (branch_metadata.get(b, {}).get('order') or 9999, b),
    )
    if not branches:
        raise CommercialDailyReportError("No branches")

    # Monthly historical MTD is authoritative at month close. Weekly
    # comparison covers the previous two calendar months and the current one;
    # it does not reconstruct the unreliable January-February daily history.
    comparison_start = (
        _three_month_window_start(cutoff)
        if metric == "reactivaciones" else FIRST_SUPPORTED_DATE
    )
    # Every weekly column must begin on Sunday and end on Saturday,
    # including the week which contains the 1st of the earliest month.
    # Include the day before that Sunday's MTD to derive its true delta.
    first_week_start = _week_start(comparison_start)
    if metric == "reactivaciones":
        series_start = max(
            FIRST_SUPPORTED_DATE, first_week_start - timedelta(days=1)
        )
        daily = {
            branch: _daily_deltas(
                {
                    day: value for day, value in mtd_series[branch].items()
                    if series_start <= day <= cutoff
                },
                historical_corrections_before=cutoff.replace(day=1),
            )
            for branch in branches
        }
    else:
        daily = {b: _daily_deltas(mtd_series[b]) for b in branches}
    week = _week_start(cutoff)
    weeks = []
    cursor = first_week_start
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
            valid_days = [
                start + timedelta(days=i) for i in range(7)
                if (
                    (first_week_start if metric == "reactivaciones" else comparison_start)
                    <= start + timedelta(days=i) <= cutoff
                )
            ]
            values = [daily[b].get(d) for d in valid_days]
            weekly_cells[b].append(
                sum(values) if valid_days and all(v is not None for v in values)
                else None
            )
        monthly_cells[b] = []
        for month in months:
            expected_day = (
                cutoff if (month.year, month.month) == (cutoff.year, cutoff.month)
                else (month.replace(day=28) + timedelta(days=4)).replace(day=1)
                - timedelta(days=1)
            )
            current = mtd_series[b].get(expected_day)
            if (
                metric == "reactivaciones"
                and historical_monthly_by_branch is not None
                and date(2026, 1, 1) <= month <= date(2026, 4, 1)
            ):
                historical = historical_monthly_by_branch.get(b, {}).get(month)
                if historical is None:
                    raise CommercialDailyReportError(
                        f"Historical Reactivaciones baseline missing: {b} {month}"
                    )
                if month in (date(2026, 1, 1), date(2026, 2, 1)):
                    # Explicit historical-source exception. January/February
                    # Track KPI snapshots (176/162, 2026-05-06) diverge from
                    # the later archived BI workbook's underlying "Sheet" data.
                    # This applies to *this report only*; Track remains intact.
                    current = historical
                else:
                    # March/April agree with the original Excel historical
                    # evidence. Fail closed if a non-null Track close diverges.
                    if current is not None and int(current) != int(historical):
                        raise CommercialDailyReportError(
                            f"Historical Reactivaciones conflict with Track: "
                            f"{b} {month} track={current} baseline={historical}"
                        )
                    current = historical
            monthly_cells[b].append(current)

    stream = BytesIO()
    book = xlsxwriter.Workbook(stream, {"in_memory": True})
    book.set_properties({"title": f"Reporte {METRICS[metric][1]} {cutoff.isoformat()}"})
    daily_title = (
        f"REACTIVACIONES · SEMANA {week:%d/%m/%Y} - "
        f"{week + timedelta(days=6):%d/%m/%Y} · CORTE {cutoff:%d/%m/%Y}"
        if metric == "reactivaciones" else None
    )
    weekly_title = (
        "REACTIVACIONES · COMPARATIVO SEMANAL "
        f"{first_week_start:%d/%m/%Y} AL {cutoff:%d/%m/%Y}"
        if metric == "reactivaciones" else None
    )
    monthly_title = (
        f"REACTIVACIONES · ACUMULADO MENSUAL AL {cutoff:%d/%m/%Y}"
        if metric == "reactivaciones" else None
    )
    _format_sheet(
        book, "Diario",
        ["Sucursal"] + [d.strftime("%d/%m/%Y") for d in day_headers],
        branches, daily_cells, branch_metadata, title_text=daily_title,
    )
    _format_sheet(
        book, "Semanal",
        ["Sucursal"] + [
            f"{w:%d/%m}-{w + timedelta(days=6):%d/%m}"
            + (
                f" (corte {cutoff:%d/%m})"
                if w == week and cutoff < w + timedelta(days=6)
                else ""
            )
            for w in weeks
        ],
        branches, weekly_cells, branch_metadata, title_text=weekly_title,
    )
    if metric == "reactivaciones":
        # A missing/negative historical correction is NOT zero. The cell and
        # its affected subtotals remain blank, and the report explains why.
        week_sheet = book.get_worksheet_by_name("Semanal")
        note_row = week_sheet.dim_rowmax + 2
        week_sheet.merge_range(
            note_row, 0, note_row, len(weeks),
            "Nota: las celdas vacías significan datos diarios faltantes "
            "o correcciones históricas; no representan cero. "
            "Todas las semanas son domingo-sábado. "
            "La última puede tener datos solo hasta el corte.",
            book.add_format({
                "italic": True, "font_color": "#6E4C00",
                "bg_color": "#FFF0CC", "text_wrap": True,
                "valign": "vcenter",
            }),
        )
        week_sheet.set_row(note_row, 34)
    monthly_number_counts = Counter(m.month for m in months)
    _format_sheet(
        book, "Totales Mensuales",
        ["Sucursal"] + [
            (
                MONTH_NAMES_ES[m.month - 1]
                + (f" {m.year}" if monthly_number_counts[m.month] > 1 else "")
            ) if metric == "reactivaciones" else m.strftime("%m/%Y")
            for m in months
        ],
        branches, monthly_cells, branch_metadata, title_text=monthly_title,
        center_summary_numbers=(metric == "reactivaciones"),
        center_headers=(metric == "reactivaciones"),
    )
    book.close()
    return stream.getvalue()


def build_commercial_daily_xlsx(*, metric: str, cutoff: date) -> bytes:
    if metric not in METRICS:
        raise ValueError(metric)
    branch_metadata = _load_branch_metadata()
    return render_commercial_daily_xlsx(
        metric=metric,
        cutoff=cutoff,
        mtd_series=_load_series(
            metric, cutoff, active_branches=set(branch_metadata),
        ),
        branch_metadata=branch_metadata,
        historical_monthly_by_branch=(
            load_early_reactivaciones_monthly()
            if metric == "reactivaciones" else None
        ),
    )
