from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.system_daily_check import (
    SystemDailyCheckIssueAttachmentORM,
    SystemDailyCheckIssueORM,
)
from app.services.system_daily_check_attachment_storage_service import (
    build_system_daily_check_attachment_storage_key,
    delete_system_daily_check_attachment,
    write_system_daily_check_attachment_bytes,
)
from app.services.system_daily_check_service import (
    SystemDailyCheckNotFoundError,
    SystemDailyCheckValidationError,
)


MAX_SYSTEM_DAILY_CHECK_ATTACHMENT_BYTES = 15 * 1024 * 1024
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
class ValidatedSystemDailyCheckAttachment:
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
    if not filename or filename in {".", ".."} or "\x00" in filename:
        raise SystemDailyCheckValidationError("Nombre de archivo inválido.")
    if len(filename) > 255:
        raise SystemDailyCheckValidationError(
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
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(
                BytesIO(content),
                formats=_ALLOWED_IMAGE_FORMATS,
            ) as image:
                detected_format = str(image.format or "").upper()
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
        raise SystemDailyCheckValidationError(
            "El archivo no es una imagen válida."
        ) from exc

    if detected_format not in _IMAGE_INFO:
        raise SystemDailyCheckValidationError(
            "Formato de imagen no permitido."
        )

    mime_type, canonical_extension, extensions, declared_mimes = (
        _IMAGE_INFO[detected_format]
    )
    if extension not in extensions:
        raise SystemDailyCheckValidationError(
            "La extensión no coincide con el formato real."
        )
    if declared_mime and declared_mime not in declared_mimes:
        raise SystemDailyCheckValidationError(
            "El MIME declarado no coincide con el archivo."
        )
    return mime_type, canonical_extension


def validate_system_daily_check_attachment(
    *,
    content: bytes,
    original_filename: str,
    declared_mime_type: str | None = None,
) -> ValidatedSystemDailyCheckAttachment:
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("content debe ser bytes")

    content_bytes = bytes(content)
    size_bytes = len(content_bytes)
    if size_bytes == 0:
        raise SystemDailyCheckValidationError(
            "No se puede adjuntar un archivo vacío."
        )
    if size_bytes > MAX_SYSTEM_DAILY_CHECK_ATTACHMENT_BYTES:
        raise SystemDailyCheckValidationError(
            "El archivo excede el límite máximo de 15 MB."
        )

    filename = _clean_filename(original_filename)
    extension = PurePosixPath(filename).suffix.lower()
    declared_mime = str(declared_mime_type or "").strip().lower()

    if content_bytes.startswith(b"%PDF-"):
        if extension != ".pdf":
            raise SystemDailyCheckValidationError(
                "La extensión no coincide con el PDF real."
            )
        if declared_mime and declared_mime != "application/pdf":
            raise SystemDailyCheckValidationError(
                "El MIME declarado no coincide con el PDF."
            )
        if not content_bytes.rstrip().endswith(b"%%EOF"):
            raise SystemDailyCheckValidationError(
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

    return ValidatedSystemDailyCheckAttachment(
        original_filename=filename,
        content=content_bytes,
        mime_type=mime_type,
        extension=canonical_extension,
        size_bytes=size_bytes,
        sha256=hashlib.sha256(content_bytes).hexdigest(),
    )


def create_system_daily_check_issue_attachment(
    *,
    issue_id: int,
    content: bytes,
    original_filename: str,
    declared_mime_type: str | None,
    actor,
    session: Session | None = None,
) -> tuple[SystemDailyCheckIssueAttachmentORM, str]:
    validated = validate_system_daily_check_attachment(
        content=content,
        original_filename=original_filename,
        declared_mime_type=declared_mime_type,
    )
    target_session = _session(session)

    issue = target_session.get(
        SystemDailyCheckIssueORM,
        int(issue_id),
    )
    if issue is None:
        raise SystemDailyCheckNotFoundError(
            "Incidencia de checklist no encontrada."
        )

    storage_key = build_system_daily_check_attachment_storage_key(
        issue.id,
        validated.extension,
    )
    attachment = SystemDailyCheckIssueAttachmentORM(
        issue_id=issue.id,
        original_filename=validated.original_filename,
        storage_key=storage_key,
        mime_type=validated.mime_type,
        file_size_bytes=validated.size_bytes,
        sha256=validated.sha256,
        uploaded_by_user_id=int(actor.id),
    )

    target_session.add(attachment)
    target_session.flush()
    write_system_daily_check_attachment_bytes(
        storage_key,
        validated.content,
    )
    return attachment, storage_key


def cleanup_system_daily_check_attachments(
    storage_keys: list[str],
) -> None:
    for storage_key in storage_keys:
        try:
            delete_system_daily_check_attachment(storage_key)
        except (OSError, ValueError):
            pass
