from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from uuid import uuid4


_STORAGE_KEY_RE = re.compile(
    r"^purchase-requisitions/(?P<requisition_id>[1-9]\d*)/"
    r"(?P<filename>[a-f0-9]{32}\.[a-z0-9]{1,10})$"
)
_EXTENSION_RE = re.compile(r"^\.[a-z0-9]{1,10}$")


def get_purchase_requisition_attachment_root() -> Path:
    configured = (
        os.getenv("PURCHASE_REQUISITION_ATTACHMENT_DIR") or ""
    ).strip()
    if configured:
        root = Path(configured)
    else:
        backend_root = Path(__file__).resolve().parents[2]
        root = (
            backend_root
            / "runtime"
            / "purchase-requisition-attachments"
        )
    return root.expanduser().resolve()


def build_purchase_requisition_attachment_storage_key(
    requisition_id: int,
    extension: str,
) -> str:
    try:
        normalized_id = int(requisition_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("requisition_id inválido") from exc
    if normalized_id <= 0:
        raise ValueError(
            "requisition_id debe ser mayor que cero"
        )

    normalized_extension = str(extension or "").strip().lower()
    if (
        normalized_extension
        and not normalized_extension.startswith(".")
    ):
        normalized_extension = f".{normalized_extension}"
    if not _EXTENSION_RE.fullmatch(normalized_extension):
        raise ValueError("Extensión de archivo inválida")

    return (
        f"purchase-requisitions/{normalized_id}/"
        f"{uuid4().hex}{normalized_extension}"
    )


def validate_purchase_requisition_attachment_storage_key(
    storage_key: str,
) -> str:
    normalized = str(storage_key or "").strip().replace("\\", "/")
    if not _STORAGE_KEY_RE.fullmatch(normalized):
        raise ValueError("storage_key inválido")

    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError("storage_key inválido")
    return normalized


def resolve_purchase_requisition_attachment_path(
    storage_key: str,
) -> Path:
    normalized = (
        validate_purchase_requisition_attachment_storage_key(
            storage_key
        )
    )
    root = get_purchase_requisition_attachment_root()
    target = root.joinpath(
        *PurePosixPath(normalized).parts
    ).resolve()

    if target == root or root not in target.parents:
        raise ValueError(
            "Ruta de adjunto fuera del almacenamiento permitido"
        )
    return target


def write_purchase_requisition_attachment_bytes(
    storage_key: str,
    content: bytes,
) -> Path:
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("content debe ser bytes")
    if not content:
        raise ValueError(
            "No se puede almacenar un archivo vacío"
        )

    target = resolve_purchase_requisition_attachment_path(
        storage_key
    )
    if target.exists():
        raise FileExistsError(
            f"El adjunto ya existe: {storage_key}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
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
            temp_file.write(bytes(content))
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, target)
        temp_path = None
        try:
            target.chmod(0o640)
        except OSError:
            pass
        return target
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def delete_purchase_requisition_attachment(
    storage_key: str,
) -> bool:
    target = resolve_purchase_requisition_attachment_path(
        storage_key
    )
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
