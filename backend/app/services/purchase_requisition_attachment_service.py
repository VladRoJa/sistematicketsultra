from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.purchase_requisition import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionEventType,
    PurchaseRequisitionORM,
)
from app.services.purchase_requisition_attachment_storage_service import (
    build_purchase_requisition_attachment_storage_key,
    delete_purchase_requisition_attachment,
    resolve_purchase_requisition_attachment_path,
    write_purchase_requisition_attachment_bytes,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionNotFoundError,
    PurchaseRequisitionValidationError,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    can_purchase_requisition_view,
    can_upload_purchase_requisition_attachment,
)


MAX_PURCHASE_REQUISITION_ATTACHMENT_BYTES = 15 * 1024 * 1024
ATTACHMENT_TYPES = ("EVIDENCE", "QUOTE", "OTHER")

_ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")
_IMAGE_INFO = {
    "JPEG": (
        "image/jpeg",
        ".jpg",
        {".jpg", ".jpeg"},
        {"image/jpeg", "image/jpg"},
    ),
    "PNG": (
        "image/png",
        ".png",
        {".png"},
        {"image/png"},
    ),
    "WEBP": (
        "image/webp",
        ".webp",
        {".webp"},
        {"image/webp"},
    ),
}


@dataclass(frozen=True)
class ValidatedPurchaseRequisitionAttachment:
    original_filename: str
    content: bytes
    mime_type: str
    extension: str
    size_bytes: int
    sha256: str


def _session(session: Session | None):
    return session if session is not None else db.session


def _clean_filename(value: object) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    filename = PurePosixPath(raw).name.strip()
    if (
        not filename
        or filename in {".", ".."}
        or "\x00" in filename
    ):
        raise PurchaseRequisitionValidationError(
            "Nombre de archivo inválido."
        )
    if len(filename) > 255:
        raise PurchaseRequisitionValidationError(
            "El nombre del archivo excede 255 caracteres."
        )
    return filename


def _validate_image(
    content: bytes,
    filename: str,
    declared_mime: str,
) -> tuple[str, str]:
    extension = PurePosixPath(filename).suffix.lower()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning,
            )
            with Image.open(
                BytesIO(content),
                formats=_ALLOWED_IMAGE_FORMATS,
            ) as image:
                detected_format = str(
                    image.format or ""
                ).upper()
                image.verify()

            with Image.open(
                BytesIO(content),
                formats=_ALLOWED_IMAGE_FORMATS,
            ) as image:
                image.load()
    except (
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
    ) as exc:
        raise PurchaseRequisitionValidationError(
            "El archivo no es una imagen válida."
        ) from exc

    if detected_format not in _IMAGE_INFO:
        raise PurchaseRequisitionValidationError(
            "Formato de imagen no permitido."
        )

    mime_type, canonical_extension, extensions, declared_mimes = (
        _IMAGE_INFO[detected_format]
    )
    if extension not in extensions:
        raise PurchaseRequisitionValidationError(
            "La extensión no coincide con el formato real."
        )
    if declared_mime and declared_mime not in declared_mimes:
        raise PurchaseRequisitionValidationError(
            "El MIME declarado no coincide con el archivo."
        )
    return mime_type, canonical_extension


def validate_purchase_requisition_attachment(
    *,
    content: bytes,
    original_filename: str,
    declared_mime_type: str | None = None,
) -> ValidatedPurchaseRequisitionAttachment:
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("content debe ser bytes")

    content_bytes = bytes(content)
    size_bytes = len(content_bytes)
    if size_bytes == 0:
        raise PurchaseRequisitionValidationError(
            "No se puede adjuntar un archivo vacío."
        )
    if size_bytes > MAX_PURCHASE_REQUISITION_ATTACHMENT_BYTES:
        raise PurchaseRequisitionValidationError(
            "El archivo excede el límite máximo de 15 MB."
        )

    filename = _clean_filename(original_filename)
    extension = PurePosixPath(filename).suffix.lower()
    declared_mime = str(
        declared_mime_type or ""
    ).strip().lower()

    if content_bytes.startswith(b"%PDF-"):
        if extension != ".pdf":
            raise PurchaseRequisitionValidationError(
                "La extensión no coincide con el PDF real."
            )
        if (
            declared_mime
            and declared_mime != "application/pdf"
        ):
            raise PurchaseRequisitionValidationError(
                "El MIME declarado no coincide con el PDF."
            )
        if not content_bytes.rstrip().endswith(b"%%EOF"):
            raise PurchaseRequisitionValidationError(
                "El PDF está incompleto o no es válido."
            )
        mime_type = "application/pdf"
        canonical_extension = ".pdf"
    else:
        mime_type, canonical_extension = _validate_image(
            content_bytes,
            filename,
            declared_mime,
        )

    return ValidatedPurchaseRequisitionAttachment(
        original_filename=filename,
        content=content_bytes,
        mime_type=mime_type,
        extension=canonical_extension,
        size_bytes=size_bytes,
        sha256=hashlib.sha256(content_bytes).hexdigest(),
    )


def _normalize_attachment_type(value: object) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in ATTACHMENT_TYPES:
        raise PurchaseRequisitionValidationError(
            "attachment_type inválido."
        )
    return normalized


def create_purchase_requisition_attachment(
    *,
    requisition_id: int,
    attachment_type: object,
    content: bytes,
    original_filename: str,
    declared_mime_type: str | None,
    actor,
    session: Session | None = None,
) -> PurchaseRequisitionAttachmentORM:
    validated = validate_purchase_requisition_attachment(
        content=content,
        original_filename=original_filename,
        declared_mime_type=declared_mime_type,
    )
    normalized_type = _normalize_attachment_type(
        attachment_type
    )
    target_session = _session(session)

    requisition = target_session.execute(
        select(PurchaseRequisitionORM)
        .where(
            PurchaseRequisitionORM.id
            == int(requisition_id)
        )
        .with_for_update()
    ).scalar_one_or_none()
    if requisition is None:
        raise PurchaseRequisitionNotFoundError(
            "Requisición no encontrada."
        )
    if not can_upload_purchase_requisition_attachment(
        actor,
        requisition,
        normalized_type,
    ):
        raise PurchaseRequisitionAuthorizationError(
            "No tienes permiso para adjuntar ese tipo de archivo "
            "en el estado actual."
        )

    storage_key = (
        build_purchase_requisition_attachment_storage_key(
            requisition.id,
            validated.extension,
        )
    )
    attachment = PurchaseRequisitionAttachmentORM(
        requisition_id=requisition.id,
        attachment_type=normalized_type,
        original_filename=validated.original_filename,
        storage_key=storage_key,
        mime_type=validated.mime_type,
        size_bytes=validated.size_bytes,
        sha256=validated.sha256,
        uploaded_by_user_id=int(actor.id),
    )

    file_written = False
    try:
        target_session.add(attachment)
        target_session.flush()

        event = PurchaseRequisitionEventORM(
            requisition_id=requisition.id,
            event_type=PurchaseRequisitionEventType.ATTACHMENT_ADDED,
            actor_user_id=int(actor.id),
            from_status=requisition.status,
            to_status=requisition.status,
            metadata_json={
                "attachment_id": int(attachment.id),
                "attachment_type": normalized_type,
                "original_filename": validated.original_filename,
            },
        )
        target_session.add(event)
        target_session.flush()
        attachment.event_id = event.id
        target_session.flush()

        write_purchase_requisition_attachment_bytes(
            storage_key,
            validated.content,
        )
        file_written = True

        target_session.commit()
        return attachment
    except Exception:
        target_session.rollback()
        if file_written:
            delete_purchase_requisition_attachment(
                storage_key
            )
        raise


def get_purchase_requisition_attachment_file(
    *,
    requisition_id: int,
    attachment_id: int,
    actor,
    session: Session | None = None,
) -> tuple[PurchaseRequisitionAttachmentORM, Path]:
    target_session = _session(session)
    requisition = target_session.get(
        PurchaseRequisitionORM,
        int(requisition_id),
    )
    if requisition is None:
        raise PurchaseRequisitionNotFoundError(
            "Requisición no encontrada."
        )
    if not can_purchase_requisition_view(
        actor,
        requisition,
    ):
        raise PurchaseRequisitionAuthorizationError(
            "No tienes acceso a esta requisición."
        )

    attachment = target_session.get(
        PurchaseRequisitionAttachmentORM,
        int(attachment_id),
    )
    if (
        attachment is None
        or int(attachment.requisition_id)
        != int(requisition.id)
        or attachment.deleted_at is not None
    ):
        raise PurchaseRequisitionNotFoundError(
            "Adjunto no encontrado."
        )

    path = resolve_purchase_requisition_attachment_path(
        attachment.storage_key
    )
    if not path.is_file():
        raise PurchaseRequisitionNotFoundError(
            "Archivo adjunto no disponible."
        )
    return attachment, path
