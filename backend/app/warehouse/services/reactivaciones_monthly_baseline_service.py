"""Immutable early-2026 monthly Reactivaciones baseline from original BI Excel.

Original workbook:
  Reporte VN - BAJAS - REACTIVACIONES 2024-MTD 2026.xlsx
  worksheet: Reactivaciones; columns Z:AC
  SHA-256: aea6d4efefcd6a18a0bb23cd147814fc8ecdf216efb14f2d5b195d39a9683d55

May, June, July values in that same source sum to 3064, 3284 and 3139,
respectively, matching the current Track close totals. Do not derive
daily reactivations from these monthly historical aggregates.
"""
from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from pathlib import Path

MONTH_COLUMNS = ("2026-01", "2026-02", "2026-03", "2026-04")
BASELINE_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "reactivaciones_monthly_2026_jan_apr.csv"
)


class ReactivacionesMonthlyBaselineError(RuntimeError):
    pass


def load_early_reactivaciones_monthly() -> dict[str, dict[date, int]]:
    """Validate immutable per-branch historical monthly counts (no DB writes)."""
    lines = BASELINE_FILE.read_text(encoding="utf-8").splitlines()
    reader = csv.DictReader(
        StringIO("\n".join(line for line in lines if not line.startswith("#")))
    )
    if reader.fieldnames != ["branch", *MONTH_COLUMNS]:
        raise ReactivacionesMonthlyBaselineError("Unexpected baseline CSV columns")

    monthly: dict[str, dict[date, int]] = {}
    for row in reader:
        branch = (row["branch"] or "").strip()
        if not branch or branch in monthly:
            raise ReactivacionesMonthlyBaselineError(
                f"Missing/duplicate historical branch: {branch!r}"
            )
        values = {}
        for label in MONTH_COLUMNS:
            raw = row[label]
            if raw is None or not raw.isascii() or not raw.isdecimal():
                raise ReactivacionesMonthlyBaselineError(
                    f"Non-integer historical value for {branch} in {label}"
                )
            values[date.fromisoformat(f"{label}-01")] = int(raw)
        monthly[branch] = values

    if len(monthly) != 26:
        raise ReactivacionesMonthlyBaselineError(
            f"Expected 26 historical branches; found {len(monthly)}"
        )
    expected_totals = (4311, 2684, 3789, 2684)
    totals = tuple(
        sum(values[date.fromisoformat(f"{label}-01")] for values in monthly.values())
        for label in MONTH_COLUMNS
    )
    if totals != expected_totals:
        raise ReactivacionesMonthlyBaselineError(
            f"Historical baseline totals changed: {totals}"
        )
    return monthly
