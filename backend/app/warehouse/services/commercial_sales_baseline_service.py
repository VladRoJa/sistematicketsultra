"""Preserve source workbook history; append only post-baseline new contracts.

The 2026-10-04 workbook is an immutable source of truth for its historical
weekly/monthly cells. Track is consulted only for newer business dates.
"""
from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from copy import copy
import hashlib
import unicodedata

from openpyxl import load_workbook
from app.models.warehouse import TrackDailyMartORM, TrackBranchCatalogORM
from app.warehouse.services.track_daily_version_service import get_current_track_daily_version

BASELINE = Path(__file__).resolve().parents[1] / "templates" / "venta_nueva_base_2026-10-04.xlsx"
BASELINE_SHA256 = "7531a7b80e70b8fda71c0d57c9281b8d14305b890b0fe7df67fa8d1c037c0b8e"
BASELINE_DAY = date(2026, 10, 4)
FIRST_NEW_DAY = date(2026, 10, 5)
FIRST_WEEK = date(2026, 10, 4)
MONTHLY_LAST_BASELINE = date(2026, 8, 1)


class SalesBaselineError(RuntimeError):
    pass


def _canon(value):
    text = unicodedata.normalize("NFKD", str(value or "")).upper()
    return "".join(ch for ch in text if ch.isalnum() and not unicodedata.combining(ch))


def _load_source():
    if not BASELINE.is_file():
        raise SalesBaselineError(f"Missing immutable sales workbook: {BASELINE}")
    data = BASELINE.read_bytes()
    if hashlib.sha256(data).hexdigest() != BASELINE_SHA256:
        raise SalesBaselineError("Baseline workbook SHA256 differs; refusing to publish")
    return load_workbook(BytesIO(data))


def _source_rows(book):
    weekly = book["Semanal"]
    monthly = book["Totales Mensuales"]
    day = book["DIARIO 04 OCT"]
    weekly_rows = {
        _canon(weekly.cell(r, 1).value): r
        for r in [*range(3, 24), *range(25, 29), 32]
    }
    monthly_rows = {
        _canon(monthly.cell(r, 2).value): r
        for r in [*range(3, 24), *range(26, 31)]
    }
    daily_rows = {
        _canon(day.cell(r, 2).value): r
        for r in [*range(3, 24), *range(25, 30)]
    }
    return weekly_rows, monthly_rows, daily_rows


def _fetch_new_data(cutoff, source_keys):
    # The canonical chosen for each day is the same source as Track daily.
    by_day = {}
    for offset in range((cutoff - date(2026, 9, 30)).days + 1):
        day = date(2026, 9, 30) + timedelta(days=offset)
        versions = [
            get_current_track_daily_version(track_date=day, version_type=t)
            for t in ("cierre_canonico", "base_nocturna_canonica")
        ]
        version = next((v for v in versions if v is not None and v.status == "success"), None)
        if version is None:
            if day >= FIRST_NEW_DAY:
                raise SalesBaselineError(f"Missing canonical Track on {day}")
            continue
        rows = TrackDailyMartORM.query.filter_by(track_daily_version_id=version.id).all()
        by_day[day] = {
            _canon(row.sucursal_canon): row.clientes_nuevos_real_mtd
            for row in rows
        }
    return by_day


def build_sales_from_baseline(*, cutoff: date) -> bytes:
    if cutoff < BASELINE_DAY:
        raise SalesBaselineError("Cutoff predates immutable source workbook")
    workbook = _load_source()
    weekly = workbook["Semanal"]
    monthly = workbook["Totales Mensuales"]
    daily = workbook["DIARIO 04 OCT"]
    wrows, mrows, drows = _source_rows(workbook)
    catalogs = TrackBranchCatalogORM.query.filter_by(is_track_active=True).all()
    # Prefer canonical branch key, falling back to the display label and
    # the old workbook's visible branch name.
    aliases = {}
    for entry in catalogs:
        names = [_canon(entry.sucursal_canon), _canon(entry.track_label)]
        for name in names:
            if name:
                aliases[name] = _canon(entry.track_label)
    def resolve(row_name):
        key = _canon(row_name)
        return aliases.get(key, key)

    source_keys = {resolve(k) for k in set(wrows) | set(mrows) | set(drows)}
    by_day_raw = _fetch_new_data(cutoff, source_keys)
    daily_changes = {}
    for day in sorted(by_day_raw):
        if day < FIRST_NEW_DAY:
            continue
        before = by_day_raw.get(day - timedelta(days=1))
        current = by_day_raw[day]
        if before is None:
            raise SalesBaselineError(f"No previous MTD for {day}")
        changes = {}
        for raw_key, amount in current.items():
            k = resolve(raw_key)
            previous = before.get(raw_key)
            if amount is None or previous is None:
                raise SalesBaselineError(f"Missing MTD {day} {raw_key}")
            delta = int(amount) - (0 if day.day == 1 else int(previous))
            if delta < 0:
                raise SalesBaselineError(f"Negative post-baseline daily delta {day}: {raw_key}={delta}")
            changes[k] = delta
        daily_changes[day] = changes

    # Build the current-week daily sheet. Leave the immutable 4 October value
    # untouched, and append daily cuts for Oct 5 onwards.
    current_week = cutoff - timedelta(days=(cutoff.weekday() + 1) % 7)
    baseline_oct4 = {key: daily.cell(row, 3).value for key, row in drows.items()}
    new_days = [current_week + timedelta(days=i) for i in range(7)]
    for col, business_day in enumerate(new_days, start=3):
        daily.cell(2, col).value = business_day
        if business_day == BASELINE_DAY:
            continue
        if business_day > cutoff:
            continue
        changes = daily_changes.get(business_day)
        if changes is None:
            raise SalesBaselineError(f"Missing daily data for {business_day}")
        for key, row in drows.items():
            resolved = resolve(key)
            if resolved not in changes:
                raise SalesBaselineError(f"Branch missing for {business_day}: {key}")
            daily.cell(row, col).value = changes[resolved]
        daily.cell(24, col).value = sum(daily.cell(r, col).value or 0 for r in range(3, 24))
        daily.cell(30, col).value = sum(daily.cell(r, col).value or 0 for r in range(25, 30))
        daily.cell(31, col).value = daily.cell(24, col).value + daily.cell(30, col).value

    # Do not modify any baseline historical week; append only new weeks.
    cursor = FIRST_WEEK
    last_closed_week = cutoff - timedelta(days=(cutoff.weekday() + 1) % 7)
    weekly_col = 37  # AK onward: retain AJ original average in place.
    while cursor <= last_closed_week:
        end = min(cursor + timedelta(days=6), cutoff)
        weekly.cell(2, weekly_col).value = f"{cursor:%d/%m} - {cursor + timedelta(days=6):%d/%m}"
        for key, row in wrows.items():
            branch = resolve(key)
            values = []
            for d in (cursor + timedelta(days=i) for i in range((end - cursor).days + 1)):
                if d == BASELINE_DAY:
                    original = baseline_oct4.get(key)
                    values.append(original)
                elif d in daily_changes:
                    values.append(daily_changes[d].get(branch))
                else:
                    values.append(None)
            if any(v is None for v in values):
                raise SalesBaselineError(f"Missing new weekly source for {key} {cursor}")
            weekly.cell(row, weekly_col).value = sum(values)
        for target_row, members in [
            (24, list(range(3, 24))),
            (29, list(range(25, 29))),
            (30, [24, 29]),
            (34, [30, 32]),
        ]:
            vals = [weekly.cell(r, weekly_col).value for r in members]
            weekly.cell(target_row, weekly_col).value = sum(v or 0 for v in vals)
        weekly_col += 1
        cursor += timedelta(days=7)

    # Monthly historical cells Jan 2025–Aug 2026 remain byte-equivalent in
    # value. September 2026 and later are sourced from canonical Track MTD.
    month = date(2026, 9, 1)
    month_col = 23  # W; V contains August 2026 in the baseline
    while month <= cutoff.replace(day=1):
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = min(next_month - timedelta(days=1), cutoff)
        readings = by_day_raw.get(month_end)
        if readings is None:
            # September is not backfilled from a different historical source.
            # Do not fabricate values for a missing canonical cutoff.
            month_col += 1
            month = next_month
            continue
        monthly.cell(2, month_col).value = month
        for key, row in mrows.items():
            resolved = resolve(key)
            candidate = next((v for k, v in readings.items() if resolve(k) == resolved), None)
            if candidate is None:
                raise SalesBaselineError(f"Missing monthly MTD {key} {month_end}")
            monthly.cell(row, month_col).value = int(candidate)
        monthly.cell(25, month_col).value = sum(monthly.cell(r, month_col).value or 0 for r in range(3, 25))
        monthly.cell(31, month_col).value = sum(monthly.cell(r, month_col).value or 0 for r in range(26, 31))
        monthly.cell(32, month_col).value = monthly.cell(25, month_col).value + monthly.cell(31, month_col).value
        month_col += 1
        month = next_month

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
