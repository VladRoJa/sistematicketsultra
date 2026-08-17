from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from uuid import uuid4


_STORAGE_KEY_RE = re.compile(
    r"^tickets/(?P<ticket_id>[1-9]\d*)/(?P<filename>[a-f0-9]{32}\.[a-z0-9]{1,10})$"
)

_EXTENSION_RE = re.compile(r"^\.[a-z0-9]{1,10}$")


def get_ticket_attachment_root() -> Path:
    """
    Directorio privado donde viven físicamente los adjuntos.

    Producción:
        TICKET_ATTACHMENT_DIR=/app/runtime/ticket-attachments

    Desarrollo local:
        backend/runtime/ticket-attachments
    """
    configured = (os.getenv("TICKET_ATTACHMENT_DIR") or "").strip()

    if configured:
        root = Path(configured)
    else:
        backend_root = Path(__file__).resolve().parents[2]
        root = backend_root / "runtime" / "ticket-attachments"

    return root.expanduser().resolve()


def build_ticket_attachment_storage_key(
    ticket_id: int,
    extension: str,
) -> str:
    """
    Genera una clave interna no predecible basada en UUID.

    Ejemplo:
        tickets/123/9fe4...b82a.png
    """
    try:
        normalized_ticket_id = int(ticket_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("ticket_id inválido") from exc

    if normalized_ticket_id <= 0:
        raise ValueError("ticket_id debe ser mayor que cero")

    normalized_extension = (extension or "").strip().lower()

    if normalized_extension and not normalized_extension.startswith("."):
        normalized_extension = f".{normalized_extension}"

    if not _EXTENSION_RE.fullmatch(normalized_extension):
        raise ValueError("Extensión de archivo inválida")

    return (
        f"tickets/{normalized_ticket_id}/"
        f"{uuid4().hex}{normalized_extension}"
    )


def validate_ticket_attachment_storage_key(storage_key: str) -> str:
    """
    Valida que la clave tenga exclusivamente el formato generado
    internamente por Suite Ultra.
    """
    normalized = (storage_key or "").strip().replace("\\", "/")

    if not _STORAGE_KEY_RE.fullmatch(normalized):
        raise ValueError("storage_key inválido")

    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError("storage_key inválido")

    return normalized


def resolve_ticket_attachment_path(storage_key: str) -> Path:
    """
    Convierte storage_key a ruta física garantizando que permanezca
    dentro del directorio privado configurado.
    """
    normalized = validate_ticket_attachment_storage_key(storage_key)
    root = get_ticket_attachment_root()

    target = root.joinpath(*PurePosixPath(normalized).parts).resolve()

    if target == root or root not in target.parents:
        raise ValueError("Ruta de adjunto fuera del almacenamiento permitido")

    return target


def write_ticket_attachment_bytes(
    storage_key: str,
    content: bytes,
) -> Path:
    """
    Escribe el archivo de forma atómica.

    Nunca sobrescribe un archivo existente.
    """
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("content debe ser bytes")

    if len(content) == 0:
        raise ValueError("No se puede almacenar un archivo vacío")

    target = resolve_ticket_attachment_path(storage_key)

    if target.exists():
        raise FileExistsError(
            f"El adjunto ya existe: {storage_key}"
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=".upload-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, target)
        temp_path = None

        try:
            target.chmod(0o640)
        except OSError:
            # En Windows los permisos POSIX no son equivalentes.
            pass

        return target

    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def ticket_attachment_exists(storage_key: str) -> bool:
    return resolve_ticket_attachment_path(storage_key).is_file()


def delete_ticket_attachment(storage_key: str) -> bool:
    """
    Eliminación física idempotente.

    Returns:
        True  -> existía y fue eliminado.
        False -> ya no existía.
    """
    target = resolve_ticket_attachment_path(storage_key)

    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
