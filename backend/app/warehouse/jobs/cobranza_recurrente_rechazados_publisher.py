# backend/app/warehouse/jobs/cobranza_recurrente_rechazados_publisher.py

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)

REPORT_TYPE_KEY = "cobranza_recurrente_rechazados"
JOB_KEY = "cobranza_recurrente_rechazados"
XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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

        artifact_uploads.append(
            {
                "sucursal_raw": sucursal_raw,
                "rows_count": rows_count,
                "upload": upload,
            }
        )

    return {
        "raw_upload": raw_upload,
        "artifact_uploads": artifact_uploads,
        "total_uploads": 1 + len(artifact_uploads),
    }