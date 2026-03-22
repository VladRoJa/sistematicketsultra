# backend/app/warehouse/services/warehouse_document_upload_service.py

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
import hashlib
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    WarehouseSourceORM,
    WarehouseFamilyORM,
    WarehouseOperationalRoleORM,
    WarehouseReportTypeORM,
    WarehouseUploadORM,
)
from app.utils.warehouse_audit import log_warehouse_audit


ALLOWED_WAREHOUSE_EXTENSIONS = {"xlsx", "xls", "csv", "pdf", "txt"}
MAX_WAREHOUSE_FILE_SIZE_BYTES = 70 * 1024 * 1024


class WarehouseDocumentUploadError(RuntimeError):
    """Error base del servicio reusable de upload documental."""


class WarehouseDocumentValidationError(WarehouseDocumentUploadError):
    """Error de validación de datos de entrada."""


def _coerce_date(value: Any, field_name: str) -> date | None:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise WarehouseDocumentValidationError(
                f"El campo '{field_name}' debe tener formato YYYY-MM-DD."
            ) from exc

    raise WarehouseDocumentValidationError(
        f"El campo '{field_name}' tiene un tipo no soportado."
    )


def _resolve_period_data(
    *,
    report_type: WarehouseReportTypeORM,
    cutoff_date: date | None,
    date_from: date | None,
    date_to: date | None,
) -> dict[str, date | None]:
    if report_type.default_period_type == "diario":
        if not cutoff_date:
            raise WarehouseDocumentValidationError(
                "Debes enviar 'cutoff_date' cuando el report_type requiere periodo diario."
            )

    if report_type.default_period_type == "rango":
        if not date_from or not date_to:
            raise WarehouseDocumentValidationError(
                "Debes enviar 'date_from' y 'date_to' cuando el report_type requiere periodo rango."
            )

        if date_from > date_to:
            raise WarehouseDocumentValidationError(
                "date_from no puede ser mayor que date_to."
            )

    return {
        "cutoff_date": cutoff_date,
        "date_from": date_from,
        "date_to": date_to,
    }


def _build_warehouse_storage_paths(
    *,
    source_key: str,
    report_type_key: str,
    anchor_date: date,
    stored_filename: str,
) -> tuple[Path, Path]:
    year = anchor_date.strftime("%Y")
    month = anchor_date.strftime("%m")

    relative_dir = Path("uploads") / "warehouse" / source_key / report_type_key / year / month
    absolute_dir = (Path(current_app.root_path).parent.parent / relative_dir).resolve()
    absolute_dir.mkdir(parents=True, exist_ok=True)

    absolute_file_path = absolute_dir / stored_filename
    return relative_dir, absolute_file_path


def _read_file_bytes(
    *,
    file_path: str | None,
    file_bytes: bytes | None,
) -> bytes:
    if file_bytes is not None:
        return file_bytes

    if file_path:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise WarehouseDocumentValidationError(
                f"No existe el archivo indicado en file_path: {path}"
            )
        return path.read_bytes()

    raise WarehouseDocumentValidationError(
        "Debes enviar 'file_path' o 'file_bytes'."
    )


def _calculate_sha256(file_content: bytes) -> str:
    return hashlib.sha256(file_content).hexdigest()


def _validate_filename_and_extension(original_filename: str) -> tuple[str, str]:
    if not original_filename:
        raise WarehouseDocumentValidationError(
            "El archivo enviado no tiene nombre válido."
        )

    safe_original_filename = secure_filename(original_filename)
    if not safe_original_filename:
        raise WarehouseDocumentValidationError(
            "No se pudo normalizar el nombre del archivo."
        )

    extension = (
        original_filename.rsplit(".", 1)[-1].lower()
        if "." in original_filename
        else ""
    )

    if extension not in ALLOWED_WAREHOUSE_EXTENSIONS:
        raise WarehouseDocumentValidationError(
            f"La extensión '{extension or 'sin extensión'}' no está permitida para Warehouse."
        )

    return safe_original_filename, extension


def create_warehouse_document_upload(
    *,
    report_type_key: str,
    original_filename: str,
    content_type: str | None = None,
    file_path: str | None = None,
    file_bytes: bytes | None = None,
    uploaded_by_user_id: int,
    cutoff_date: date | str | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    audit_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Servicio reusable de creación de uploads documentales en Warehouse.

    Este servicio encapsula la lógica real de:
    - validación
    - guardado físico
    - creación de WarehouseUploadORM
    - auditoría

    Puede ser usado tanto por el route manual como por el pipeline interno.
    """
    if not isinstance(uploaded_by_user_id, int) or uploaded_by_user_id <= 0:
        raise WarehouseDocumentValidationError(
            "'uploaded_by_user_id' debe ser un entero positivo."
        )

    report_type_key = (report_type_key or "").strip()
    if not report_type_key:
        raise WarehouseDocumentValidationError(
            "Debes enviar 'report_type_key'."
        )

    safe_original_filename, extension = _validate_filename_and_extension(
        original_filename
    )

    file_content = _read_file_bytes(
        file_path=file_path,
        file_bytes=file_bytes,
    )

    file_size = len(file_content)
    if file_size > MAX_WAREHOUSE_FILE_SIZE_BYTES:
        raise WarehouseDocumentValidationError(
            "El archivo excede el tamaño máximo permitido de 70 MB para Warehouse."
        )

    report_type = WarehouseReportTypeORM.query.filter_by(
        key=report_type_key,
        active=True,
    ).first()

    if not report_type:
        raise WarehouseDocumentValidationError(
            f"El report_type_key '{report_type_key}' no existe o no está activo en Warehouse."
        )

    if (
        not report_type.default_source_id
        or not report_type.default_operational_role_id
        or not report_type.family_id
    ):
        raise WarehouseDocumentValidationError(
            f"El report_type_key '{report_type_key}' no tiene configuración base completa en Warehouse."
        )

    source = WarehouseSourceORM.query.filter_by(
        id=report_type.default_source_id,
        active=True,
    ).first()
    family = WarehouseFamilyORM.query.filter_by(
        id=report_type.family_id,
        active=True,
    ).first()
    operational_role = WarehouseOperationalRoleORM.query.filter_by(
        id=report_type.default_operational_role_id,
        active=True,
    ).first()

    if not source or not family or not operational_role:
        raise WarehouseDocumentValidationError(
            f"El report_type_key '{report_type_key}' referencia catálogos inactivos o inexistentes."
        )

    parsed_cutoff_date = _coerce_date(cutoff_date, "cutoff_date")
    parsed_date_from = _coerce_date(date_from, "date_from")
    parsed_date_to = _coerce_date(date_to, "date_to")

    period_data = _resolve_period_data(
        report_type=report_type,
        cutoff_date=parsed_cutoff_date,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
    )

    period_anchor_date = period_data["cutoff_date"] or period_data["date_from"]
    if not period_anchor_date:
        raise WarehouseDocumentValidationError(
            "No se pudo determinar la fecha base del periodo documental."
        )

    file_hash_sha256 = _calculate_sha256(file_content)

    duplicate_upload = (
        WarehouseUploadORM.query
        .filter_by(file_hash_sha256=file_hash_sha256)
        .order_by(WarehouseUploadORM.created_at.desc())
        .first()
    )

    stored_filename = f"{uuid.uuid4()}_{safe_original_filename}"

    relative_dir, absolute_file_path = _build_warehouse_storage_paths(
        source_key=source.key,
        report_type_key=report_type.key,
        anchor_date=period_anchor_date,
        stored_filename=stored_filename,
    )

    try:
        absolute_file_path.write_bytes(file_content)

        upload = WarehouseUploadORM(
            original_filename=original_filename,
            stored_filename=stored_filename,
            stored_path=str(relative_dir).replace("\\", "/"),
            file_size_bytes=file_size,
            file_hash_sha256=file_hash_sha256,
            mime_type=content_type,
            extension=extension,
            source_id=source.id,
            family_id=family.id,
            operational_role_id=operational_role.id,
            report_type_id=report_type.id,
            period_type=report_type.default_period_type,
            cutoff_date=period_data["cutoff_date"],
            date_from=period_data["date_from"],
            date_to=period_data["date_to"],
            status="ACTIVE",
            uploaded_by_user_id=uploaded_by_user_id,
        )

        db.session.add(upload)
        db.session.flush()

        log_warehouse_audit(
            action="UPLOAD",
            performed_by_user_id=uploaded_by_user_id,
            upload_id=upload.id,
            details={
                "original_filename": original_filename,
                "stored_filename": stored_filename,
                "report_type_key": report_type.key,
                "period_type": report_type.default_period_type,
                **(audit_details or {}),
            },
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        if absolute_file_path.exists():
            absolute_file_path.unlink()

        raise

    return {
        "upload_id": upload.id,
        "warehouse_upload_id": upload.id,
        "filename": original_filename,
        "stored_filename": stored_filename,
        "stored_path": str(relative_dir).replace("\\", "/"),
        "file_size_bytes": file_size,
        "file_hash_sha256": file_hash_sha256,
        "report_type_key": report_type.key,
        "report_type_id": report_type.id,
        "family_id": family.id,
        "source_id": source.id,
        "operational_role_id": operational_role.id,
        "period_type": report_type.default_period_type,
        "cutoff_date": (
            period_data["cutoff_date"].isoformat()
            if period_data["cutoff_date"]
            else None
        ),
        "date_from": (
            period_data["date_from"].isoformat()
            if period_data["date_from"]
            else None
        ),
        "date_to": (
            period_data["date_to"].isoformat()
            if period_data["date_to"]
            else None
        ),
        "duplicate_detected": duplicate_upload is not None,
        "duplicate_upload_id": duplicate_upload.id if duplicate_upload else None,
        "upload_status": "created",
    }