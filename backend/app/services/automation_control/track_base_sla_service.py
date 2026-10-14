"""Ratified Track nightly-base SLA, read-only and independent of canonical close.

Business date D: due 02:00 D+1, late 03:00 D+1 in America/Tijuana.
Applies every calendar day. No green until historical branch coverage is
certified. Schedule defaults, retry and canonical-close timing are separate.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.warehouse import TrackDailyMartORM, TrackDailyVersionORM
from app.services.automation_control.track_coverage_service import assess_version_rows
from app.warehouse.services.track_daily_mart_service import _load_active_analytical_branches

TIJUANA = ZoneInfo("America/Tijuana")
BASE_DUE = time(2, 0)
BASE_LATE = time(3, 0)


def _local_boundary(day: date, at: time) -> datetime:
    """Normalize nonexistent local times when spring DST skips 02:00.

    In a skipped hour, 02:00 becomes the first real instant (03:00).
    Compare via UTC; never create a fictitious 60-minute window.
    """
    local = datetime.combine(day, at, tzinfo=TIJUANA)
    return local.astimezone(timezone.utc).astimezone(TIJUANA)


def base_sla_window(*, business_date: date, now: datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    tomorrow = business_date + timedelta(days=1)
    due = _local_boundary(tomorrow, BASE_DUE)
    late = _local_boundary(tomorrow, BASE_LATE)
    instant = now.astimezone(timezone.utc)
    phase = (
        "NOT_DUE" if instant < due.astimezone(timezone.utc)
        else "LAGGING" if instant < late.astimezone(timezone.utc)
        else "LATE"
    )
    return {
        "expected_business_date": business_date.isoformat(),
        "due_at": due.isoformat(),
        "late_at": late.isoformat(),
        "phase_if_unavailable": phase,
        "timezone": TIJUANA.key,
        "policy_key": "TRACK_BASE_DAILY_D_PLUS_1_0200_0300_V1",
        "applies_every_day": True,
    }


def read_track_base_sla(*, business_date: date, now: datetime) -> dict:
    """Inspect current base, never use preview/cierre to certify the base.

    Missing or non-successful current base can be marked pending/late.
    If base succeeds, historical roster remains unverified, so health is
    UNKNOWN rather than an unsupported green or red classification.
    """
    result = base_sla_window(business_date=business_date, now=now)
    versions = db.session.query(
        TrackDailyVersionORM.id, TrackDailyVersionORM.status,
    ).filter(
        TrackDailyVersionORM.track_date == business_date,
        TrackDailyVersionORM.version_type == "base_nocturna_canonica",
        TrackDailyVersionORM.is_current.is_(True),
    ).all()
    result.update({
        "status": "UNKNOWN",
        "reason_code": "BASE_VERSION_UNVERIFIED",
        "base_version_id": None,
        "base_version_status": None,
        "base_current_catalog_coverage": None,
        "historical_roster_verified": False,
        "canonical_close_sla": "SEPARATE_CONDITIONAL_NOT_RATIFIED",
    })
    if len(versions) > 1:
        result["reason_code"] = "AMBIGUOUS_CURRENT_BASE"
        return result

    version = versions[0] if versions else None
    if version:
        version_id, version_status = version
        result["base_version_id"] = version_id
        result["base_version_status"] = version_status

    if version and version[1] == "success":
        branches = _load_active_analytical_branches()
        codes = [branch.sucursal_canon for branch in branches]
        rows = db.session.query(
            TrackDailyMartORM.track_daily_version_id,
            TrackDailyMartORM.sucursal_canon,
            TrackDailyMartORM.track_date,
            TrackDailyMartORM.generation_mode,
        ).filter(TrackDailyMartORM.track_daily_version_id == version[0]).all()
        compared = assess_version_rows(
            expected_branches=set(codes), version_id=version[0],
            track_date=business_date, mart_rows=[tuple(row) for row in rows],
        )
        # Current catalog could contain duplicate branch identifiers; don't
        # consider that a match against any version.
        if len(codes) != len(set(codes)):
            compared["matches_current_catalog"] = False
        result["base_current_catalog_coverage"] = compared
        if result["phase_if_unavailable"] == "NOT_DUE":
            result["status"] = "NOT_DUE"
            result["reason_code"] = "BASE_DUE_TIME_NOT_REACHED"
        else:
            result["reason_code"] = "BASE_SUCCESS_ROSTER_HISTORY_UNVERIFIED"
        return result

    result["status"] = result["phase_if_unavailable"]
    result["reason_code"] = (
        "BASE_CURRENT_NOT_SUCCESS" if version else "NO_CURRENT_BASE"
    )
    return result
