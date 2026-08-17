from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.extensions import db
from app.models.ticket_attachment import TicketAttachmentORM


TICKET_ATTACHMENT_RETENTION_DAYS = 30


def _normalize_utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("finalized_at debe ser datetime")

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def schedule_ticket_attachment_retention(
    *,
    ticket_id: int,
    finalized_at: datetime | None = None,
) -> tuple[int, datetime]:
    """
    Programa la eliminación física de los adjuntos activos de un ticket.

    Regla:
        delete_after = instante real de finalización + 30 días

    Este servicio NO hace commit. El caller debe incluir esta actualización
    en la misma transacción que cambia el ticket a estado finalizado.

    Returns:
        (cantidad_adjuntos_programados, delete_after)
    """
    try:
        normalized_ticket_id = int(ticket_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("ticket_id inválido") from exc

    if normalized_ticket_id <= 0:
        raise ValueError("ticket_id inválido")

    closure_at = _normalize_utc_datetime(
        finalized_at or datetime.now(timezone.utc)
    )

    delete_after = closure_at + timedelta(
        days=TICKET_ATTACHMENT_RETENTION_DAYS
    )

    statement = (
        select(TicketAttachmentORM)
        .where(
            TicketAttachmentORM.ticket_id == normalized_ticket_id,
            TicketAttachmentORM.deleted_at.is_(None),
        )
        .order_by(TicketAttachmentORM.id.asc())
    )

    attachments = list(
        db.session.scalars(statement).all()
    )

    for attachment in attachments:
        attachment.delete_after = delete_after

    return len(attachments), delete_after
