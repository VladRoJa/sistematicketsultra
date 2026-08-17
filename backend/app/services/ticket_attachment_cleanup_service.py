from datetime import datetime, timezone

from sqlalchemy import select

from app.extensions import db
from app.models.ticket_attachment import TicketAttachmentORM
from app.services.ticket_attachment_storage_service import (
    delete_ticket_attachment,
)


DEFAULT_TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE = 100
MAX_TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE = 1000


def _normalize_cleanup_datetime(
    value: datetime,
) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("now debe ser datetime")

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _normalize_cleanup_limit(limit: int) -> int:
    try:
        normalized = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit inválido") from exc

    if (
        normalized <= 0
        or normalized > MAX_TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE
    ):
        raise ValueError("limit inválido")

    return normalized


def cleanup_expired_ticket_attachments(
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE,
) -> dict:
    """
    Elimina físicamente adjuntos cuya retención ya venció.

    Es idempotente:
    - si el archivo existe, lo elimina;
    - si ya no existe, igualmente marca deleted_at;
    - si un archivo puntual falla, no bloquea los demás;
    - nunca elimina la fila de metadata.

    La función hace un único commit por lote cuando existe al menos
    un adjunto procesado correctamente.
    """
    cutoff = _normalize_cleanup_datetime(
        now or datetime.now(timezone.utc)
    )
    normalized_limit = _normalize_cleanup_limit(limit)

    statement = (
        select(TicketAttachmentORM)
        .where(
            TicketAttachmentORM.deleted_at.is_(None),
            TicketAttachmentORM.delete_after.is_not(None),
            TicketAttachmentORM.delete_after <= cutoff,
        )
        .order_by(
            TicketAttachmentORM.delete_after.asc(),
            TicketAttachmentORM.id.asc(),
        )
        .limit(normalized_limit)
    )

    attachments = list(
        db.session.scalars(statement).all()
    )

    result = {
        "examined": len(attachments),
        "marked_deleted": 0,
        "files_deleted": 0,
        "files_already_missing": 0,
        "failed": [],
    }

    for attachment in attachments:
        try:
            physically_deleted = delete_ticket_attachment(
                attachment.storage_key
            )
        except (OSError, ValueError) as exc:
            result["failed"].append({
                "attachment_id": attachment.id,
                "error": str(exc),
            })
            continue

        if physically_deleted:
            result["files_deleted"] += 1
        else:
            result["files_already_missing"] += 1

        attachment.deleted_at = cutoff
        result["marked_deleted"] += 1

    if result["marked_deleted"] > 0:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    return result
