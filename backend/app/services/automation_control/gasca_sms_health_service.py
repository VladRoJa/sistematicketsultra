"""Visibilidad de la cola SMS Gasca sin PIN, teléfonos, códigos ni navegador.

El estado del worker se obtiene por heartbeat separado; un último SMS enviado
no confirma que Google Messages siga vinculado en este instante.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models.rpa import GascaSmsRequestORM, GascaSmsRequestStatus as Status


_ACTIVE = (
    Status.GASCA_SEARCHING,
    Status.READY_TO_SEND,
    Status.SMS_SENDING,
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def read_gasca_sms_queue(now: datetime | None = None) -> dict:
    """Dos agregados acotados; no leer filas de clientes ni logs de envío."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    table = GascaSmsRequestORM
    backlog = dict(
        db.session.query(table.status, func.count(table.id))
        .filter(table.status.in_((Status.PENDING, *_ACTIVE)))
        .group_by(table.status).all()
    )
    since = now - timedelta(hours=24)
    recent = dict(
        db.session.query(table.status, func.count(table.id))
        .filter(table.created_at >= since)
        .group_by(table.status).all()
    )
    last_sent = db.session.query(func.max(table.sent_at)).filter(
        table.status == Status.SENT
    ).scalar()
    last_failed = db.session.query(func.max(table.processed_at)).filter(
        table.status == Status.FAILED
    ).scalar()

    return {
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "coverage": "REQUEST_STATUSES",
        "session_status": "UNVERIFIED",
        "session_reason": "NO_SAFE_BROWSER_PROBE",
        "pending": int(backlog.get(Status.PENDING, 0)),
        "in_progress": sum(int(backlog.get(status, 0)) for status in _ACTIVE),
        "sent_last_24h": int(recent.get(Status.SENT, 0)),
        "failed_last_24h": int(recent.get(Status.FAILED, 0)),
        "last_sent_at_utc": _iso(last_sent),
        "last_failed_at_utc": _iso(last_failed),
    }
