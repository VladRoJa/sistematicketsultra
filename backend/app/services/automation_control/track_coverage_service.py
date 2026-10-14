"""Track mart coverage against the current, non-demo analytical branch catalog.

Read-only evidence. The catalog has no effective dating, so a match cannot
certify the branch roster at an older business date or a business SLA.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from app.extensions import db
from app.models.warehouse import TrackDailyMartORM, TrackDailyVersionORM
from app.warehouse.services.track_daily_mart_service import (
    _load_active_analytical_branches,
)


def assess_version_rows(
    *, expected_branches: set[str], version_id: int,
    track_date: date, mart_rows: list[tuple],
) -> dict:
    """Pure coverage logic. A version can only cover its exact official date."""
    seen: Counter[str] = Counter()
    invalid_date = 0
    wrong_mode = 0
    for row in mart_rows:
        if row[0] != version_id:
            raise ValueError("Unexpected mart version in bounded reader")
        branch, row_date, mode = row[1], row[2], row[3]
        seen[branch] += 1
        invalid_date += row_date != track_date
        wrong_mode += mode != "official_closed_day"

    actual = set(seen)
    missing = sorted(expected_branches - actual)
    unexpected = sorted(actual - expected_branches)
    duplicates = sorted(key for key, count in seen.items() if count > 1)
    matches = (
        bool(expected_branches) and not missing and not unexpected
        and not duplicates and not invalid_date and not wrong_mode
    )
    return {
        "matches_current_catalog": matches,
        "expected_branch_count": len(expected_branches),
        "actual_branch_count": len(actual),
        "mart_row_count": len(mart_rows),
        "missing_branch_codes": missing,
        "unexpected_branch_codes": unexpected,
        "duplicate_branch_codes": duplicates,
        "wrong_date_row_count": invalid_date,
        "wrong_generation_mode_row_count": wrong_mode,
        "roster_basis": "CURRENT_TRACK_CATALOG_NON_DEMO",
        "historical_roster_verified": False,
    }


def read_track_current_catalog_coverage(*, cutoff: date) -> dict:
    """Bounded to 15 business dates and max one selected version/date.

    Base nocturna is a fallback if the current cierre canónico does not exist;
    only successful current versions are eligible. A duplicate eligible version
    of the same type makes that day ambiguous and never certifiable.
    """
    branches = _load_active_analytical_branches()
    codes = [row.sucursal_canon for row in branches]
    expected = set(codes)
    valid_catalog = bool(expected) and len(expected) == len(codes)

    version_rows = db.session.query(
        TrackDailyVersionORM.id,
        TrackDailyVersionORM.track_date,
        TrackDailyVersionORM.version_type,
    ).filter(
        TrackDailyVersionORM.track_date.between(cutoff - timedelta(days=14), cutoff),
        TrackDailyVersionORM.is_current.is_(True),
        TrackDailyVersionORM.status == "success",
        TrackDailyVersionORM.version_type.in_((
            "base_nocturna_canonica", "cierre_canonico",
        )),
    ).all()
    grouped: dict[date, list[tuple[int, str]]] = {}
    for version_id, business_date, kind in version_rows:
        grouped.setdefault(business_date, []).append((version_id, kind))
    selected: dict[date, tuple[int, str]] = {}
    ambiguous: set[date] = set()
    for business_date, choices in grouped.items():
        highest = max(1 if kind == "cierre_canonico" else 0 for _, kind in choices)
        candidates = [
            (vid, kind) for vid, kind in choices
            if (1 if kind == "cierre_canonico" else 0) == highest
        ]
        if len(candidates) != 1:
            ambiguous.add(business_date)
        else:
            selected[business_date] = candidates[0]

    ids = [vid for vid, _ in selected.values()]
    mart_rows = (
        db.session.query(
            TrackDailyMartORM.track_daily_version_id,
            TrackDailyMartORM.sucursal_canon,
            TrackDailyMartORM.track_date,
            TrackDailyMartORM.generation_mode,
        ).filter(TrackDailyMartORM.track_daily_version_id.in_(ids)).all()
        if ids else []
    )
    by_id: dict[int, list[tuple]] = {vid: [] for vid in ids}
    for row in mart_rows:
        if row[0] in by_id:
            by_id[row[0]].append(tuple(row))
    latest_match = None
    evaluations: dict[date, dict] = {}
    for day, (vid, kind) in selected.items():
        evaluated = assess_version_rows(
            expected_branches=expected, version_id=vid,
            track_date=day, mart_rows=by_id[vid],
        )
        if not valid_catalog:
            evaluated["matches_current_catalog"] = False
        evaluated["selected_version_type"] = kind
        evaluated["selected_version_id"] = vid
        evaluations[day] = evaluated
        if evaluated["matches_current_catalog"] and (
            latest_match is None or day > latest_match
        ):
            latest_match = day
    latest_day = max(grouped) if grouped else None
    selected_day = max(selected) if selected else None
    if latest_day in ambiguous:
        observed = {
            "matches_current_catalog": False,
            "expected_branch_count": len(expected),
            "actual_branch_count": None,
            "mart_row_count": None,
            "missing_branch_codes": [],
            "unexpected_branch_codes": [],
            "duplicate_branch_codes": [],
            "wrong_date_row_count": None,
            "wrong_generation_mode_row_count": None,
            "roster_basis": "CURRENT_TRACK_CATALOG_NON_DEMO",
            "historical_roster_verified": False,
            "selected_version_type": None,
            "selected_version_id": None,
        }
    else:
        observed = evaluations.get(latest_day)
    return {
        "latest_selected_version_date": latest_day.isoformat() if latest_day else None,
        "latest_catalog_matched_date": latest_match.isoformat() if latest_match else None,
        "selected_version_count": len(selected),
        "ambiguous_current_version_dates": [
            day.isoformat() for day in sorted(ambiguous)
        ],
        "current_catalog_valid": valid_catalog,
        "coverage": observed,
        "roster_basis": "CURRENT_TRACK_CATALOG_NON_DEMO",
        "historical_roster_verified": False,
    }
