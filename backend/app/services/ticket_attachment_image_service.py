from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError


MAX_TICKET_ATTACHMENT_BYTES = 15 * 1024 * 1024

_ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")

_FORMAT_INFO = {
    "JPEG": {
        "mime_type": "image/jpeg",
        "extension": ".jpg",
        "extensions": {".jpg", ".jpeg"},
        "declared_mimes": {"image/jpeg", "image/jpg"},
    },
    "PNG": {
        "mime_type": "image/png",
        "extension": ".png",
        "extensions": {".png"},
        "declared_mimes": {"image/png"},
    },
    "WEBP": {
        "mime_type": "image/webp",
        "extension": ".webp",
        "extensions": {".webp"},
        "declared_mimes": {"image/webp"},
    },
}


@dataclass(frozen=True)
class ValidatedTicketAttachmentImage:
    original_filename: str
    content: bytes
    format: str
    mime_type: str
    extension: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    optimization_mode: str = "original"


def _clean_original_filename(original_filename: str) -> str:
    """
    Conserva únicamente el nombre visible del archivo.

    También elimina prefijos tipo C:\\fakepath\\ que algunos navegadores
    pueden entregar.
    """
    value = str(original_filename or "").strip()

    if not value:
        raise ValueError("El archivo debe tener nombre")

    value = value.replace("\\", "/")
    filename = PurePosixPath(value).name.strip()

    if not filename or filename in {".", ".."}:
        raise ValueError("Nombre de archivo inválido")

    if "\x00" in filename:
        raise ValueError("Nombre de archivo inválido")

    if len(filename) > 255:
        raise ValueError("El nombre del archivo excede 255 caracteres")

    return filename


def _filename_extension(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix
    return suffix.lower()


def validate_ticket_attachment_image(
    *,
    content: bytes,
    original_filename: str,
    declared_mime_type: str | None = None,
) -> ValidatedTicketAttachmentImage:
    """
    Valida un adjunto de imagen sin modificar sus bytes.

    Reglas V1:
    - máximo 15 MiB;
    - únicamente JPEG, PNG o WebP;
    - formato detectado por Pillow, no por extensión;
    - extensión del nombre debe coincidir con el formato real;
    - MIME declarado, si existe, debe ser compatible;
    - archivo debe poder verificarse y decodificarse;
    - DecompressionBombWarning se trata como error.
    """
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("content debe ser bytes")

    content_bytes = bytes(content)
    size_bytes = len(content_bytes)

    if size_bytes == 0:
        raise ValueError("No se puede adjuntar un archivo vacío")

    if size_bytes > MAX_TICKET_ATTACHMENT_BYTES:
        raise ValueError(
            "La imagen excede el límite máximo de 15 MB"
        )

    filename = _clean_original_filename(original_filename)
    extension = _filename_extension(filename)

    declared_mime = (declared_mime_type or "").strip().lower()

    try:
        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning,
            )

            # Primera apertura: validación estructural.
            with Image.open(
                BytesIO(content_bytes),
                formats=_ALLOWED_FORMATS,
            ) as image:
                detected_format = str(image.format or "").upper()
                width, height = image.size

                image.verify()

            # Segunda apertura: comprobar que los datos de imagen
            # realmente pueden decodificarse.
            with Image.open(
                BytesIO(content_bytes),
                formats=_ALLOWED_FORMATS,
            ) as image:
                image.load()

    except Image.DecompressionBombWarning as exc:
        raise ValueError(
            "La imagen excede los límites seguros de dimensiones"
        ) from exc
    except Image.DecompressionBombError as exc:
        raise ValueError(
            "La imagen excede los límites seguros de dimensiones"
        ) from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError(
            "El archivo no es una imagen JPEG, PNG o WebP válida"
        ) from exc

    if detected_format not in _FORMAT_INFO:
        raise ValueError(
            "Formato de imagen no permitido"
        )

    if width <= 0 or height <= 0:
        raise ValueError(
            "La imagen tiene dimensiones inválidas"
        )

    info = _FORMAT_INFO[detected_format]

    if extension not in info["extensions"]:
        raise ValueError(
            "La extensión del archivo no coincide con "
            "el formato real de la imagen"
        )

    if (
        declared_mime
        and declared_mime not in info["declared_mimes"]
    ):
        raise ValueError(
            "El tipo MIME declarado no coincide con "
            "el formato real de la imagen"
        )

    return ValidatedTicketAttachmentImage(
        original_filename=filename,
        content=content_bytes,
        format=detected_format,
        mime_type=info["mime_type"],
        extension=info["extension"],
        size_bytes=size_bytes,
        width=int(width),
        height=int(height),
        sha256=hashlib.sha256(content_bytes).hexdigest(),
        optimization_mode="original",
    )
