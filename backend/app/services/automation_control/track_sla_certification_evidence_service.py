"""M1-F6 stage 4 — read-only Track base certification evidence.

NO change to `read_freshness` or public SLA semantics. The business gate
for enabling green is separate. An opening date / today's catalog is never
an adequate substitute for a sealed prospective effective-roster attestation.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.warehouse import (
    TrackDailyMartORM,
    TrackDailyVersionORM,
    TrackVersionRosterMemberORM,
    TrackVersionRosterSnapshotORM,
)
from app.services.automation_control.track_base_sla_service import base_sla_window
from app.warehouse.services.track_effective_roster_service import (
    read_effective_roster_for_date,
)
from app.warehouse.services.track_version_roster_capture_service import (
    normalized_roster, roster_digest,
)

TIJUANA = ZoneInfo("America/Tijuana")
EXPECTED_MODE = "official_closed_day"
BASE_TYPE = "base_nocturna_canonica"
MAX_BRANCHES = 500


def _unverified(reason_code: str) -> dict:
    return {
        "evidence_verified": False,
        "reason_code": reason_code,
        "historical_roster_verified": False,
        "published_at_utc": None,
        "published_on_time": None,
        "sla_status": "UNKNOWN",
        "green_activation_authorized": False,
    }


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def verify_base_publication(
    *,
    business_date: date,
    now: datetime,
    version,
    epoch: dict,
    snapshot,
    snapshot_members: list,
    mart_rows: list,
) -> dict:
    """Pure contract checking: never promote to a user-visible SLA status.

    Inputs must originate from version IDs bounded to the same day and type.
    All branch code+ID pairs must match the prospectively attested authority.
    """
    failure = _unverified
    if not epoch.get("verified"):
        return failure(epoch.get("reason_code", "NO_EFFECTIVE_ROSTER_ATTESTATION"))
    if not version or (
        version.track_date != business_date
        or version.version_type != BASE_TYPE
        or version.status != "success"
        or not version.is_current
    ):
        return failure("BASE_VERSION_NOT_CURRENT_SUCCESS")

    started = _utc(getattr(version, "started_at_utc", None))
    finished = _utc(getattr(version, "finished_at_utc", None))
    instant = _utc(now)
    attested = _utc(datetime.fromisoformat(epoch["attested_at_utc"]))
    policy_day_start = datetime.combine(business_date, time.min, tzinfo=TIJUANA)
    if (
        started is None or finished is None or instant is None or attested is None
        or started > finished or finished > instant
        or attested >= policy_day_start.astimezone(timezone.utc)
    ):
        return failure("BASE_TIME_OR_ATTESTATION_UNVERIFIED")

    if not snapshot or (
        snapshot.version_id != version.id
        or snapshot.track_date != business_date
        or snapshot.source_kind != "LIVE_TRACK_CATALOG_NON_DEMO_AT_CAPTURE"
        or snapshot.historical_roster_verified is not False
        or snapshot.sealed_at_utc is None
    ):
        return failure("VERSION_ROSTER_SNAPSHOT_UNVERIFIED")

    captured_at = _utc(snapshot.captured_at_utc)
    sealed_at = _utc(snapshot.sealed_at_utc)
    if (
        captured_at is None or sealed_at is None
        or captured_at < started or sealed_at < captured_at
        or sealed_at > finished
    ):
        return failure("VERSION_ROSTER_CAPTURE_TIME_INVALID")

    try:
        effective = normalized_roster([
            _Branch(code, identifier) for code, identifier in epoch["branches"]
        ])
        captured = normalized_roster([
            _Branch(row.sucursal_canon, row.sucursal_id_at_capture)
            for row in snapshot_members
        ])
    except (KeyError, ValueError, TypeError):
        return failure("INVALID_VERSION_OR_EFFECTIVE_ROSTER")

    if (
        not effective or len(effective) > MAX_BRANCHES
        or effective != captured
        or len(snapshot_members) != snapshot.expected_branch_count
        or len(effective) != epoch["expected_branch_count"]
        or roster_digest(effective) != epoch["roster_sha256"]
        or roster_digest(captured) != snapshot.roster_sha256
    ):
        return failure("VERSION_EFFECTIVE_ROSTER_MISMATCH")

    expected_codes = [code for code, _ in effective]
    observed_codes = [row.sucursal_canon for row in mart_rows]
    if (
        len(observed_codes) != len(expected_codes)
        or sorted(observed_codes) != expected_codes
        or any(
            row.track_daily_version_id != version.id
            or row.track_date != business_date
            or row.generation_mode != EXPECTED_MODE
            for row in mart_rows
        )
    ):
        return failure("BASE_MART_COVERAGE_UNVERIFIED")

    boundaries = base_sla_window(business_date=business_date, now=now)
    due = _utc(datetime.fromisoformat(boundaries["due_at"]))
    assert due is not None  # base_sla_window always emits aware local datetimes
    published_on_time = finished <= due
    return {
        "evidence_verified": True,
        "reason_code": (
            "BASE_ROSTER_AND_DEADLINE_EVIDENCE_COMPLETE"
            if published_on_time else "BASE_PUBLISHED_AFTER_DUE"
        ),
        "historical_roster_verified": True,  # Derived, never mutates immutable DB flag.
        "published_at_utc": finished.isoformat(),
        "published_on_time": published_on_time,
        "due_at": boundaries["due_at"],
        "late_at": boundaries["late_at"],
        "sla_status": "UNKNOWN",  # No UI green before business activation.
        "green_activation_authorized": False,
        "effective_epoch_id": epoch["epoch_id"],
        "base_version_id": version.id,
        "expected_branch_count": len(effective),
    }


class _Branch:
    def __init__(self, code: str, branch_id: int | None):
        self.sucursal_canon = code
        self.sucursal_id = branch_id


def inspect_track_base_certification_evidence(*, business_date: date, now: datetime) -> dict:
    """Read at most one current/success base, 500 members and 500 mart rows."""
    if type(business_date) is not date or _utc(now) is None:
        raise ValueError("business_date o now inválidos.")
    rows = (
        db.session.query(TrackDailyVersionORM.id)
        .filter(
            TrackDailyVersionORM.track_date == business_date,
            TrackDailyVersionORM.version_type == BASE_TYPE,
            TrackDailyVersionORM.is_current.is_(True),
            TrackDailyVersionORM.status == "success",
        )
        .limit(2).all()
    )
    if len(rows) != 1:
        return _unverified("NO_UNAMBIGUOUS_CURRENT_BASE")

    epoch = read_effective_roster_for_date(business_date)
    if not epoch.get("verified"):
        return _unverified(epoch["reason_code"])
    version_id = rows[0][0]
    version = db.session.get(TrackDailyVersionORM, version_id)
    snapshot = db.session.get(TrackVersionRosterSnapshotORM, version_id)
    members = (
        db.session.query(TrackVersionRosterMemberORM)
        .filter(TrackVersionRosterMemberORM.version_id == version_id)
        .limit(MAX_BRANCHES + 1).all()
    )
    mart = (
        db.session.query(TrackDailyMartORM)
        .filter(TrackDailyMartORM.track_daily_version_id == version_id)
        .limit(MAX_BRANCHES + 1).all()
    )
    if len(members) > MAX_BRANCHES or len(mart) > MAX_BRANCHES:
        return _unverified("TRACK_ROSTER_TOO_LARGE_TO_CERTIFY")
    return verify_base_publication(
        business_date=business_date, now=now, version=version,
        epoch=epoch, snapshot=snapshot, snapshot_members=members, mart_rows=mart,
    )
