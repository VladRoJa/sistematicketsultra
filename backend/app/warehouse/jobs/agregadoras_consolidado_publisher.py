from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from app.internal_documents.services.internal_document_publication_service import (
    add_internal_document_version_from_warehouse_upload,
    publish_internal_document_from_warehouse_upload,
)
from app.models import InternalDocumentORM, InternalDocumentStatus
from app.models.user_model import UserORM
from app.models.internal_documents import InternalDocumentVisibilityMode
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)


REPORT_TYPE_KEY = "agregadoras_consolidado"
DOCUMENT_TITLE = "Consolidado de agregadoras"
DOCUMENT_CATEGORY_KEY = "REPORTES"
DOCUMENT_TYPE = "REPORTE_FINANCIERO"
DOCUMENT_LINK_ROLE = "FINANCIERO"
XLSX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet"
)


class AgregadorasConsolidadoPublishError(RuntimeError):
    """Error publicando el consolidado de agregadoras en Warehouse/Nube."""


def _resolve_automation_user_id() -> int:
    raw_value = os.getenv("WAREHOUSE_AUTOMATION_USER_ID", "").strip()

    if not raw_value:
        raise AgregadorasConsolidadoPublishError(
            "Falta configurar WAREHOUSE_AUTOMATION_USER_ID."
        )

    try:
        user_id = int(raw_value)
    except ValueError as exc:
        raise AgregadorasConsolidadoPublishError(
            "WAREHOUSE_AUTOMATION_USER_ID debe ser un entero válido."
        ) from exc

    if user_id <= 0:
        raise AgregadorasConsolidadoPublishError(
            "WAREHOUSE_AUTOMATION_USER_ID debe ser mayor a 0."
        )

    return user_id


def _coerce_business_date(value: date | str) -> date:
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AgregadorasConsolidadoPublishError(
            f"cutoff_date inválida: {value!r}"
        ) from exc


def _extract_warehouse_upload_id(upload_result: dict[str, Any]) -> int:
    raw_id = (
        upload_result.get("warehouse_upload_id")
        or upload_result.get("upload_id")
        or upload_result.get("id")
    )

    try:
        upload_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise AgregadorasConsolidadoPublishError(
            "No se pudo resolver warehouse_upload_id desde el resultado "
            f"del upload: {upload_result!r}"
        ) from exc

    if upload_id <= 0:
        raise AgregadorasConsolidadoPublishError(
            f"warehouse_upload_id inválido: {upload_id!r}"
        )

    return upload_id


def _resolve_admicorp_user_id() -> int:
    user = UserORM.get_by_username("ADMICORP")
    if user is None or not getattr(user, "id", None):
        raise AgregadorasConsolidadoPublishError(
            "No existe el usuario ADMICORP requerido para publicar "
            "el consolidado de agregadoras."
        )

    return int(user.id)


def _find_existing_document() -> InternalDocumentORM | None:
    return (
        InternalDocumentORM.query
        .filter(InternalDocumentORM.title == DOCUMENT_TITLE)
        .filter(
            InternalDocumentORM.status
            != InternalDocumentStatus.ARCHIVED
        )
        .order_by(
            InternalDocumentORM.created_at.asc(),
            InternalDocumentORM.id.asc(),
        )
        .first()
    )


def publish_agregadoras_consolidado_output(
    *,
    file_path: str | Path,
    cutoff_date: date | str,
    download_filename: str | None = None,
) -> dict[str, Any]:
    resolved_file_path = Path(file_path)
    if not resolved_file_path.exists() or not resolved_file_path.is_file():
        raise AgregadorasConsolidadoPublishError(
            f"No existe el XLSX generado: {resolved_file_path}"
        )

    resolved_cutoff_date = _coerce_business_date(cutoff_date)
    automation_user_id = _resolve_automation_user_id()
    admicorp_user_id = _resolve_admicorp_user_id()
    original_filename = (
        str(download_filename or "").strip()
        or resolved_file_path.name
    )

    upload_result = create_warehouse_document_upload(
        report_type_key=REPORT_TYPE_KEY,
        original_filename=original_filename,
        content_type=XLSX_MIME_TYPE,
        file_path=str(resolved_file_path),
        uploaded_by_user_id=automation_user_id,
        cutoff_date=resolved_cutoff_date,
        audit_details={
            "upload_origin": "agregadoras_consolidado_generator",
            "report_type_key": REPORT_TYPE_KEY,
            "cutoff_date": resolved_cutoff_date.isoformat(),
        },
    )
    warehouse_upload_id = _extract_warehouse_upload_id(upload_result)

    audit_metadata = {
        "origin": "automation",
        "job_key": REPORT_TYPE_KEY,
        "cutoff_date": resolved_cutoff_date.isoformat(),
        "warehouse_upload_id": warehouse_upload_id,
    }

    existing_document = _find_existing_document()

    if existing_document is None:
        publication = publish_internal_document_from_warehouse_upload(
            warehouse_upload_id=warehouse_upload_id,
            title=DOCUMENT_TITLE,
            category_key=DOCUMENT_CATEGORY_KEY,
            created_by_user_id=automation_user_id,
            description=(
                "Consolidado automático de Wellhub y TotalPass "
                f"con corte {resolved_cutoff_date.isoformat()}."
            ),
            document_type=DOCUMENT_TYPE,
            is_sensitive=True,
            visibility_mode=InternalDocumentVisibilityMode.CUSTOM,
            visibility_rules=[
                {
                    "visibility_type": "USER",
                    "user_id": admicorp_user_id,
                    "can_view": True,
                    "can_download": True,
                }
            ],
            links=[
                {
                    "entity_type": "GENERAL",
                    "entity_key": "AGREGADORAS",
                    "link_role": DOCUMENT_LINK_ROLE,
                    "label": "Consolidado de agregadoras",
                    "is_primary": True,
                }
            ],
            publish_now=True,
            version_label=resolved_cutoff_date.isoformat(),
            change_notes=(
                "Publicación automática del consolidado de agregadoras "
                f"con corte {resolved_cutoff_date.isoformat()}."
            ),
            audit_metadata=audit_metadata,
        )

        return {
            "action": "document_created",
            "cutoff_date": resolved_cutoff_date.isoformat(),
            "warehouse_upload_id": warehouse_upload_id,
            "upload": upload_result,
            "publication": publication,
        }

    publication = add_internal_document_version_from_warehouse_upload(
        document_id=existing_document.id,
        warehouse_upload_id=warehouse_upload_id,
        created_by_user_id=automation_user_id,
        version_label=resolved_cutoff_date.isoformat(),
        change_notes=(
            "Actualización automática del consolidado de agregadoras "
            f"con corte {resolved_cutoff_date.isoformat()}."
        ),
        audit_metadata=audit_metadata,
    )

    return {
        "action": (
            "version_created"
            if publication.get("created")
            else "already_published"
        ),
        "cutoff_date": resolved_cutoff_date.isoformat(),
        "warehouse_upload_id": warehouse_upload_id,
        "document_id": existing_document.id,
        "upload": upload_result,
        "publication": publication,
    }
