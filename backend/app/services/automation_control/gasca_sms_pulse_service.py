"""Isolated two-hour SMS health probes; no phone number or message persisted."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.extensions import db
from app.models.automation_control import GascaSmsHealthPulseORM as Pulse

PULSE_INTERVAL_SECONDS = 2 * 60 * 60
PULSE_GRACE = timedelta(minutes=15)
PULSE_RUNNING_LIMIT = timedelta(minutes=10)


def _now(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("La fecha del pulso debe incluir zona horaria.")
    return result.astimezone(timezone.utc)


def pulse_slot_id(now: datetime | None = None) -> int:
    """Stable UTC slot; does not depend on process uptime or DST."""
    return int(_now(now).timestamp() // PULSE_INTERVAL_SECONDS)


def reserve_pulse(now: datetime | None = None) -> int | None:
    """Call only when no customer request is claimed. Commit BEFORE opening Chrome.

    STARTED survives crashes: do not resend an uncertain SMS after a restart.
    """
    stamp = _now(now)
    slot = pulse_slot_id(stamp)
    query = (
        pg_insert(Pulse)
        .values(slot_id=slot, status="STARTED", attempted_at=stamp)
        .on_conflict_do_nothing(index_elements=["slot_id"])
        .returning(Pulse.slot_id)
    )
    claimed = db.session.execute(query).scalar_one_or_none()
    db.session.commit()
    return int(claimed) if claimed is not None else None


def cancel_pulse_before_send(slot: int) -> None:
    """Re-queue the slot only if not even attempting to use Google Messages."""
    db.session.execute(
        delete(Pulse).where(Pulse.slot_id == slot, Pulse.status == "STARTED")
    )
    db.session.commit()


def finish_pulse(slot: int, *, sent: bool, error_code: str | None = None) -> None:
    """Persist one terminal outcome. Never store Playwright exception text."""
    if not sent and error_code not in {"SENDER_ERROR", "UNEXPECTED_ERROR"}:
        raise ValueError("Código de error de pulso no reconocido.")
    result = db.session.execute(
        update(Pulse)
        .where(Pulse.slot_id == slot, Pulse.status == "STARTED")
        .values(
            status="SENT" if sent else "FAILED",
            finished_at=_now(),
            error_code=None if sent else error_code,
        )
    )
    db.session.commit()
    if result.rowcount != 1:
        raise RuntimeError("El pulso no existe o ya tiene resultado terminal.")


def read_pulse_health(now: datetime | None = None) -> dict:
    """Sanitized, read-only contract; no phone, profile data, or SMS contents."""
    stamp = _now(now)
    latest = Pulse.query.order_by(Pulse.slot_id.desc()).first()
    last_sent = (
        Pulse.query.filter(Pulse.status == "SENT")
        .order_by(Pulse.slot_id.desc()).first()
    )
    if latest is None:
        state = "UNKNOWN"
    elif latest.status == "FAILED":
        state = "FAILED"
    elif latest.status == "STARTED":
        state = (
            "FAILED"
            if stamp - _now(latest.attempted_at) > PULSE_RUNNING_LIMIT
            else "RUNNING"
        )
    elif stamp - _now(latest.attempted_at) > timedelta(seconds=PULSE_INTERVAL_SECONDS) + PULSE_GRACE:
        state = "LATE"
    else:
        state = "HEALTHY"

    cutoff = last_sent.slot_id if last_sent else -1
    failures = (
        db.session.query(func.count(Pulse.slot_id))
        .filter(Pulse.status == "FAILED", Pulse.slot_id > cutoff)
        .scalar()
    ) or 0

    return {
        "checked_at_utc": stamp.isoformat(),
        "coverage": "PERSISTED_SMS_PULSE",
        "state": state,
        "interval_seconds": PULSE_INTERVAL_SECONDS,
        "last_attempt_at_utc": _now(latest.attempted_at).isoformat() if latest else None,
        "last_success_at_utc": _now(last_sent.finished_at).isoformat() if last_sent and last_sent.finished_at else None,
        "last_error_code": latest.error_code if latest and latest.status == "FAILED" else None,
        "consecutive_failures": int(failures),
        "delivery_verified": False,
    }
