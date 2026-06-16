# backend/app/warehouse/jobs/cobranza_recurrente_rechazados_publisher.py

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

from app.internal_documents.services.internal_document_publication_service import (
    publish_internal_document_from_warehouse_upload,
)
from app.models import InternalDocumentORM, InternalDocumentVisibilityMode
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)

logger = logging.getLogger(__name__)

REPORT_TYPE_KEY = "cobranza_recurrente_rechazados"
JOB_KEY = "cobranza_recurrente_rechazados"
XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

INTERNAL_DOCUMENT_CATEGORY_KEY = "REPORTES"
INTERNAL_DOCUMENT_TYPE = "REPORTE_OPERATIVO"
INTERNAL_DOCUMENT_LINK_ROLE = "FINANCIERO"


class CobranzaRecurrentePublishError(RuntimeError):
    """Error publicando artifacts de cobranza recurrente en Warehouse/Nube."""


def _resolve_automation_user_id() -> int:
    raw_value = os.getenv("WAREHOUSE_AUTOMATION_USER_ID", "").strip()

    if not raw_value:
        raise CobranzaRecurrentePublishError(
            "Falta configurar WAREHOUSE_AUTOMATION_USER_ID."
        )

    try:
        user_id = int(raw_value)
    except ValueError as exc:
        raise CobranzaRecurrentePublishError(
            "WAREHOUSE_AUTOMATION_USER_ID debe ser un entero válido."
        ) from exc

    if user_id <= 0:
        raise CobranzaRecurrentePublishError(
            "WAREHOUSE_AUTOMATION_USER_ID debe ser mayor a 0."
        )

    return user_id


def _coerce_business_date(value: date | str) -> date:
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise CobranzaRecurrentePublishError(
            f"business_date inválida: {value!r}"
        ) from exc


def _publish_single_file(
    *,
    file_path: Path,
    original_filename: str,
    business_date: date,
    uploaded_by_user_id: int,
    artifact_kind: str,
    extra_audit_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not file_path.exists() or not file_path.is_file():
        raise CobranzaRecurrentePublishError(
            f"No existe el archivo a publicar: {file_path}"
        )

    return create_warehouse_document_upload(
        report_type_key=REPORT_TYPE_KEY,
        original_filename=original_filename,
        content_type=XLSX_MIME_TYPE,
        file_path=str(file_path),
        uploaded_by_user_id=uploaded_by_user_id,
        cutoff_date=business_date,
        audit_details={
            "upload_origin": "reports_scheduler",
            "job_key": JOB_KEY,
            "artifact_kind": artifact_kind,
            "business_date": business_date.isoformat(),
            **(extra_audit_details or {}),
        },
    )


def _extract_warehouse_upload_id(upload_result: dict[str, Any]) -> int:
    raw_id = (
        upload_result.get("warehouse_upload_id")
        or upload_result.get("id")
        or upload_result.get("upload_id")
    )

    try:
        upload_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise CobranzaRecurrentePublishError(
            f"No se pudo resolver warehouse_upload_id desde: {upload_result!r}"
        ) from exc

    if upload_id <= 0:
        raise CobranzaRecurrentePublishError(
            f"warehouse_upload_id inválido: {upload_id!r}"
        )

    return upload_id


def _build_internal_document_title(
    *,
    sucursal_raw: str,
    business_date: date,
) -> str:
    clean_sucursal = sucursal_raw.strip() or "SIN SUCURSAL"

    return (
        "Cobranza recurrente rechazados - "
        f"{clean_sucursal} - {business_date.isoformat()}"
    )


def _find_existing_published_internal_document(
    *,
    title: str,
) -> InternalDocumentORM | None:
    return (
        InternalDocumentORM.query
        .filter(InternalDocumentORM.title == title)
        .filter(InternalDocumentORM.status == "PUBLICADO")
        .order_by(InternalDocumentORM.created_at.asc(), InternalDocumentORM.id.asc())
        .first()
    )


def _publish_sucursal_upload_to_internal_documents(
    *,
    warehouse_upload_id: int,
    business_date: date,
    sucursal_raw: str,
    rows_count: Any,
    uploaded_by_user_id: int,
) -> dict[str, Any]:
    clean_sucursal = sucursal_raw.strip() or "SIN SUCURSAL"

    title = _build_internal_document_title(
        sucursal_raw=clean_sucursal,
        business_date=business_date,
    )

    existing_document = _find_existing_published_internal_document(title=title)

    if existing_document:
        logger.info(
            "Documento Nube ya existe para cobranza recurrente. "
            "Se omite publicación duplicada. document_id=%s title=%s",
            existing_document.id,
            title,
        )

        return {
            "skipped": True,
            "reason": "already_published",
            "internal_document_id": existing_document.id,
            "title": title,
            "warehouse_upload_id": warehouse_upload_id,
            "sucursal_raw": clean_sucursal,
            "business_date": business_date.isoformat(),
            "rows_count": rows_count,
        }

    audit_metadata = {
        "origin": "automation",
        "job_key": JOB_KEY,
        "source": "gasca_auto",
        "business_date": business_date.isoformat(),
        "warehouse_upload_id": warehouse_upload_id,
        "sucursal_raw": clean_sucursal,
        "rows_count": rows_count,
    }

    publication_result = publish_internal_document_from_warehouse_upload(
        warehouse_upload_id=warehouse_upload_id,
        title=title,
        category_key=INTERNAL_DOCUMENT_CATEGORY_KEY,
        created_by_user_id=uploaded_by_user_id,
        description=(
            "Reporte automático de cobranza recurrente rechazada "
            f"para {clean_sucursal}, corte {business_date.isoformat()}."
        ),
        document_type=INTERNAL_DOCUMENT_TYPE,
        is_sensitive=True,
        visibility_mode=InternalDocumentVisibilityMode.PRIVATE,
        visibility_rules=None,
        links=[
            {
                "entity_type": "SUCURSAL",
                "entity_key": clean_sucursal,
                "link_role": INTERNAL_DOCUMENT_LINK_ROLE,
                "label": "Cobranza recurrente rechazados",
                "is_primary": False,
            }
        ],
        publish_now=True,
        version_label=business_date.isoformat(),
        change_notes="Publicación automática desde reporte Gasca.",
        audit_metadata=audit_metadata,
    )

    if isinstance(publication_result, dict):
        publication_result.setdefault("skipped", False)
        publication_result.setdefault("title", title)
        publication_result.setdefault("warehouse_upload_id", warehouse_upload_id)
        publication_result.setdefault("sucursal_raw", clean_sucursal)
        publication_result.setdefault("business_date", business_date.isoformat())
        publication_result.setdefault("rows_count", rows_count)

    return publication_result


def publish_cobranza_recurrente_rechazados_outputs(
    *,
    business_date: date | str,
    raw_file: str | Path,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    resolved_business_date = _coerce_business_date(business_date)
    automation_user_id = _resolve_automation_user_id()

    raw_path = Path(raw_file)

    raw_upload = _publish_single_file(
        file_path=raw_path,
        original_filename=raw_path.name,
        business_date=resolved_business_date,
        uploaded_by_user_id=automation_user_id,
        artifact_kind="raw",
        extra_audit_details={
            "source": "gasca_auto",
        },
    )

    artifact_uploads: list[dict[str, Any]] = []
    created_internal_documents: list[dict[str, Any]] = []
    skipped_internal_documents: list[dict[str, Any]] = []

    for artifact in artifacts:
        artifact_path_raw = artifact.get("path")
        if not artifact_path_raw:
            raise CobranzaRecurrentePublishError(
                f"Artifact sin path: {artifact!r}"
            )

        artifact_path = Path(str(artifact_path_raw))
        sucursal_raw = str(artifact.get("sucursal_raw") or "").strip()
        rows_count = artifact.get("rows_count")

        upload = _publish_single_file(
            file_path=artifact_path,
            original_filename=artifact.get("filename") or artifact_path.name,
            business_date=resolved_business_date,
            uploaded_by_user_id=automation_user_id,
            artifact_kind="sucursal",
            extra_audit_details={
                "source": "gasca_auto",
                "sucursal_raw": sucursal_raw,
                "rows_count": rows_count,
            },
        )

        warehouse_upload_id = _extract_warehouse_upload_id(upload)

        internal_document_publication = (
            _publish_sucursal_upload_to_internal_documents(
                warehouse_upload_id=warehouse_upload_id,
                business_date=resolved_business_date,
                sucursal_raw=sucursal_raw,
                rows_count=rows_count,
                uploaded_by_user_id=automation_user_id,
            )
        )

        if internal_document_publication.get("skipped"):
            skipped_internal_documents.append(internal_document_publication)
        else:
            created_internal_documents.append(internal_document_publication)

        artifact_uploads.append(
            {
                "sucursal_raw": sucursal_raw,
                "rows_count": rows_count,
                "upload": upload,
                "internal_document_publication": internal_document_publication,
            }
        )

    return {
        "raw_upload": raw_upload,
        "artifact_uploads": artifact_uploads,
        "total_uploads": 1 + len(artifact_uploads),
        "total_internal_documents": len(created_internal_documents),
        "total_skipped_internal_documents": len(skipped_internal_documents),
        "created_internal_documents": created_internal_documents,
        "skipped_internal_documents": skipped_internal_documents,
    }
