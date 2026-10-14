"""M1-F6 stage 3: prospective corporate attestation of Track branch membership.

An operational opening date or current Track catalog is NOT historical
evidence. Corporate must attest the branch universe for a FUTURE day.
No HTTP write route is exposed by this stage; activation needs business signoff.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.warehouse import (
    TrackEffectiveRosterEpochORM,
    TrackEffectiveRosterMemberORM,
)
from app.warehouse.services.track_daily_mart_service import (
    _load_active_analytical_branches,
)
from app.warehouse.services.track_version_roster_capture_service import (
    normalized_roster, roster_digest,
)

TIJUANA = ZoneInfo("America/Tijuana")
SOURCE_KIND = "CORPORATE_ROSTER_ATTESTATION"


class TrackEffectiveRosterError(ValueError):
    """Attestation or temporal validity is not demonstrated."""


def _authorized_actor(user) -> int:
    """Not the broad administrator role: require the ADMICORP identity."""
    name = str(getattr(user, "username", "") or "").strip().upper()
    actor_id = getattr(user, "id", None)
    if name != "ADMICORP" or type(actor_id) is not int or actor_id <= 0:
        raise TrackEffectiveRosterError("Se requiere autorización corporativa ADMICORP.")
    return actor_id


def attest_future_track_roster(
    *, effective_from: date, user, source_reference: str,
) -> dict:
    """Stage but do NOT commit an operator-reviewed prospective roster.

    Callers must explicitly authorize this action; this function is not
    wired to a route, scheduler, CLI or automatic execution in M1-F6/3.
    A migration-level guard independently rejects backdating, duplicate
    dates and inserting a new epoch before an existing later one.
    """
    actor_id = _authorized_actor(user)
    if type(effective_from) is not date:
        raise TrackEffectiveRosterError("effective_from debe ser date exacta.")
    today = datetime.now(TIJUANA).date()
    if effective_from <= today:
        raise TrackEffectiveRosterError(
            "Solo pueden atestarse vigencias futuras; sin backfill retrospectivo."
        )
    source_reference = str(source_reference or "").strip()
    if not (8 <= len(source_reference) <= 255):
        raise TrackEffectiveRosterError("Referencia documental obligatoria (8-255).")

    pairs = normalized_roster(_load_active_analytical_branches())
    digest = roster_digest(pairs)
    epoch = TrackEffectiveRosterEpochORM(
        effective_from=effective_from,
        attested_by_user_id=actor_id,
        source_reference=source_reference,
        source_kind=SOURCE_KIND,
        expected_branch_count=len(pairs),
        roster_sha256=digest,
    )
    db.session.add(epoch)
    db.session.flush()
    db.session.add_all([
        TrackEffectiveRosterMemberORM(
            epoch_id=epoch.id,
            sucursal_canon=code,
            sucursal_id_at_attestation=branch_id,
        )
        for code, branch_id in pairs
    ])
    db.session.flush()
    epoch.sealed_at_utc = db.func.current_timestamp()
    db.session.flush()
    return {
        "epoch_id": epoch.id,
        "effective_from": effective_from.isoformat(),
        "expected_branch_count": len(pairs),
        "roster_sha256": digest,
        "attested_by_user_id": actor_id,
        "source_kind": SOURCE_KIND,
        "sealed": True,
    }


def read_effective_roster_for_date(day: date) -> dict:
    """Bounded read for future SLA use; rejects missing or tampered evidence.

    A sealed prospective attestation is necessary but NEVER sufficient for
    UP_TO_DATE. The mart version, its captured members and actual publish
    timestamp must independently validate in M1-F6/4.
    """
    if type(day) is not date:
        raise TrackEffectiveRosterError("Día de negocio inválido.")
    epochs = (
        db.session.query(TrackEffectiveRosterEpochORM)
        .filter(
            TrackEffectiveRosterEpochORM.effective_from <= day,
        )
        .order_by(TrackEffectiveRosterEpochORM.effective_from.desc())
        .limit(2)
        .all()
    )
    if not epochs:
        return {"verified": False, "reason_code": "NO_EFFECTIVE_ROSTER_ATTESTATION"}
    epoch = epochs[0]
    # Never fall back to an older sealed epoch once a newer decision's
    # effective date has arrived but its member set is still unsealed.
    if epoch.sealed_at_utc is None:
        return {"verified": False, "reason_code": "EFFECTIVE_ROSTER_UNSEALED"}
    rows = (
        db.session.query(TrackEffectiveRosterMemberORM)
        .filter(TrackEffectiveRosterMemberORM.epoch_id == epoch.id)
        .limit(501)
        .all()
    )
    pairs = [(row.sucursal_canon, row.sucursal_id_at_attestation) for row in rows]
    try:
        normalized = normalized_roster([
            type("Branch", (), {"sucursal_canon": a, "sucursal_id": b})()
            for a, b in pairs
        ])
    except ValueError:
        return {"verified": False, "reason_code": "INVALID_EFFECTIVE_ROSTER"}
    if (
        len(rows) != epoch.expected_branch_count
        or len(rows) >= 501
        or roster_digest(normalized) != epoch.roster_sha256
    ):
        return {"verified": False, "reason_code": "EFFECTIVE_ROSTER_INTEGRITY_ERROR"}
    return {
        "verified": True,
        "reason_code": "EFFECTIVE_ROSTER_ATTESTED",
        "epoch_id": epoch.id,
        "effective_from": epoch.effective_from.isoformat(),
        "attested_at_utc": epoch.attested_at_utc.isoformat(),
        "sealed_at_utc": epoch.sealed_at_utc.isoformat(),
        "expected_branch_count": epoch.expected_branch_count,
        "roster_sha256": epoch.roster_sha256,
        "branches": normalized,
        "source_kind": SOURCE_KIND,
    }
