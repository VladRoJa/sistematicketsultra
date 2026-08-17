from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models.ticket_attachment import TicketAttachmentORM
from app.services.ticket_attachment_image_service import (
    validate_ticket_attachment_image,
)
from app.services.ticket_attachment_storage_service import (
    build_ticket_attachment_storage_key,
    delete_ticket_attachment,
    write_ticket_attachment_bytes,
)


def _normalize_ticket_id(ticket_id: int) -> int:
    try:
        normalized = int(ticket_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("ticket_id inválido") from exc

    if normalized <= 0:
        raise ValueError("ticket_id debe ser mayor que cero")

    return normalized


def _ticket_already_has_attachment(ticket_id: int) -> bool:
    """
    Regla V1: un ticket puede tener como máximo un adjunto.

    No se impone UNIQUE(ticket_id) en DB para conservar la posibilidad
    de soportar múltiples adjuntos en una versión futura.
    """
    statement = (
        select(TicketAttachmentORM.id)
        .where(TicketAttachmentORM.ticket_id == ticket_id)
        .limit(1)
    )

    return (
        db.session.execute(statement).scalar_one_or_none()
        is not None
    )


def create_ticket_image_attachment(
    *,
    ticket_id: int,
    content: bytes,
    original_filename: str,
    declared_mime_type: str | None = None,
) -> TicketAttachmentORM:
    """
    Valida y persiste un único adjunto de imagen para un ticket existente.

    Orden deliberado:
    1. validar imagen;
    2. validar regla de un adjunto;
    3. preparar metadata;
    4. flush DB para validar FK/constraints ANTES de escribir archivo;
    5. escribir archivo privado;
    6. commit DB.

    Si algo falla después de escribir el archivo, se hace rollback
    y eliminación física idempotente.
    """
    normalized_ticket_id = _normalize_ticket_id(ticket_id)

    validated = validate_ticket_attachment_image(
        content=content,
        original_filename=original_filename,
        declared_mime_type=declared_mime_type,
    )

    if _ticket_already_has_attachment(normalized_ticket_id):
        raise ValueError(
            "El ticket ya tiene un archivo adjunto"
        )

    storage_key = build_ticket_attachment_storage_key(
        ticket_id=normalized_ticket_id,
        extension=validated.extension,
    )

    attachment = TicketAttachmentORM(
        ticket_id=normalized_ticket_id,
        original_filename=validated.original_filename,
        storage_key=storage_key,
        mime_type=validated.mime_type,
        size_bytes=validated.size_bytes,
        width=validated.width,
        height=validated.height,
        sha256=validated.sha256,
        optimization_mode=validated.optimization_mode,
    )

    file_written = False

    try:
        db.session.add(attachment)

        # La FK y constraints deben validarse antes de tocar filesystem.
        db.session.flush()

        write_ticket_attachment_bytes(
            storage_key,
            validated.content,
        )
        file_written = True

        db.session.commit()

        return attachment

    except Exception:
        db.session.rollback()

        if file_written:
            delete_ticket_attachment(storage_key)

        raise
