"""Publish closed-day commercial reports to ADMICORP in Corporate Cloud."""
from __future__ import annotations

import os
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from flask import current_app

from app.internal_documents.services.internal_document_publication_service import (
    add_internal_document_version_from_warehouse_upload,
    publish_internal_document_from_warehouse_upload,
)
from app.models import (
    InternalDocumentORM,
    InternalDocumentVersionORM,
    InternalDocumentStatus,
    InternalDocumentVisibilityORM,
)
from app.models.user_model import UserORM
from app.warehouse.services.commercial_daily_reports_service import (
    METRICS,
    build_commercial_daily_xlsx,
)
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class CommercialDailyPublicationError(RuntimeError):
    pass


def _resolve_users() -> tuple[int, int]:
    raw = os.getenv("WAREHOUSE_AUTOMATION_USER_ID", "").strip()
    try:
        automation_id = int(raw)
    except ValueError as exc:
        raise CommercialDailyPublicationError(
            "WAREHOUSE_AUTOMATION_USER_ID is required."
        ) from exc
    if automation_id <= 0:
        raise CommercialDailyPublicationError("Invalid automation user.")
    admicorp = UserORM.get_by_username("ADMICORP")
    if admicorp is None or not getattr(admicorp, "id", None):
        raise CommercialDailyPublicationError("Missing ADMICORP account.")
    return automation_id, int(admicorp.id)


def _validate_exclusive_access(document: InternalDocumentORM, admicorp_id: int):
    if document.visibility_mode != "CUSTOM" or not document.is_sensitive:
        raise CommercialDailyPublicationError(
            "Existing report does not have restricted visibility."
        )
    rules = InternalDocumentVisibilityORM.query.filter_by(
        document_id=document.id, is_active=True
    ).all()
    if len(rules) != 1 or rules[0].visibility_type != "USER" or rules[0].user_id != admicorp_id:
        raise CommercialDailyPublicationError(
            "Existing report has unexpected visibility rules; refusing to publish."
        )


def _report_content_fingerprint(payload: bytes) -> str:
    """Compare XLSX report content without volatile Office modification metadata.

    Hash the actual XML parts rather than the ZIP container timestamps.
    This also detects corrections to styles, formulas, and worksheet values.
    """
    digest = sha256()
    try:
        with ZipFile(BytesIO(payload)) as archive:
            names = sorted(
                item.filename for item in archive.infolist()
                if not item.is_dir() and item.filename != "docProps/core.xml"
            )
            if not names:
                raise CommercialDailyPublicationError("Empty report XLSX")
            for name in names:
                digest.update(name.encode("utf-8"))
                digest.update(b"\\0")
                digest.update(archive.read(name))
                digest.update(b"\\0")
    except (BadZipFile, OSError) as exc:
        raise CommercialDailyPublicationError(
            "Cannot fingerprint the generated report XLSX"
        ) from exc
    return digest.hexdigest()


def _current_document_file(document: InternalDocumentORM) -> bytes:
    """Read the active Warehouse file; never rely on ZIP binary hashes alone."""
    version = document.current_version
    upload = version.warehouse_upload if version is not None else None
    if upload is None or not upload.stored_path or not upload.stored_filename:
        raise CommercialDailyPublicationError(
            "The current document has no readable Warehouse upload"
        )
    root = Path(current_app.root_path).parent.parent.resolve()
    path = (root / upload.stored_path / upload.stored_filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise CommercialDailyPublicationError(
            "The current document file is missing or outside Warehouse storage"
        )
    content = path.read_bytes()
    if version.file_hash_sha256 and sha256(content).hexdigest() != version.file_hash_sha256:
        raise CommercialDailyPublicationError(
            "The current document file checksum does not match its version"
        )
    return content


def _next_cutoff_version_label(
    *, cutoff: date, versions: list[InternalDocumentVersionORM]
) -> str:
    base = cutoff.isoformat()
    labels = {version.version_label for version in versions}
    if base not in labels:
        return base
    revision = 2
    while f"{base}-r{revision}" in labels:
        revision += 1
    return f"{base}-r{revision}"


def _existing_report_is_equivalent(
    document: InternalDocumentORM, payload: bytes
) -> bool:
    current = document.current_version
    if current is None:
        return False
    if current.file_hash_sha256 == sha256(payload).hexdigest():
        return True
    return (
        _report_content_fingerprint(_current_document_file(document))
        == _report_content_fingerprint(payload)
    )


def _publish_one(
    *, metric: str, cutoff: date, automation_id: int, admicorp_id: int
) -> dict[str, Any]:
    field, label = METRICS[metric]
    title = f"Reporte {label.title()}"
    report_type_key = f"comercial_{metric}_daily"
    if metric == "venta_nueva":
        report_type_key = "comercial_venta_nueva_daily"
    else:
        report_type_key = "comercial_reactivaciones_daily"

    if metric == "venta_nueva":
        from app.warehouse.services.commercial_sales_baseline_service import (
            build_sales_from_baseline,
        )
        payload = build_sales_from_baseline(cutoff=cutoff)
    else:
        payload = build_commercial_daily_xlsx(metric=metric, cutoff=cutoff)
    document = (
        InternalDocumentORM.query
        .filter(
            InternalDocumentORM.title == title,
            InternalDocumentORM.status != InternalDocumentStatus.ARCHIVED,
        )
        .order_by(InternalDocumentORM.id.asc())
        .first()
    )
    version_label = cutoff.isoformat()
    if document is not None:
        _validate_exclusive_access(document, admicorp_id)
        current = document.current_version
        if current is not None and str(current.version_label)[:10] > version_label:
            raise CommercialDailyPublicationError(
                "Cannot replace a newer report with an older cutoff"
            )
        if _existing_report_is_equivalent(document, payload):
            return {
                "metric": metric,
                "warehouse_upload_id": current.warehouse_upload_id,
                "publication": {
                    "created": False,
                    "document_id": document.id,
                    "version_id": current.id,
                    "version_label": current.version_label,
                    "message": "Current report already has the same content.",
                },
            }
        version_label = _next_cutoff_version_label(
            cutoff=cutoff, versions=document.versions
        )

    upload_result = create_warehouse_document_upload(
        report_type_key=report_type_key,
        original_filename=f"{report_type_key}_{cutoff.isoformat()}.xlsx",
        content_type=MIME,
        file_bytes=payload,
        uploaded_by_user_id=automation_id,
        cutoff_date=cutoff,
        audit_details={
            "origin": "track_canonical",
            "job_key": "commercial_daily_reports",
            "metric_field": field,
            "cutoff_date": cutoff.isoformat(),
        },
    )
    upload_id = int(upload_result["warehouse_upload_id"])
    metadata = {
        "origin": "automation",
        "job_key": "commercial_daily_reports",
        "metric": metric,
        "business_date": cutoff.isoformat(),
        "warehouse_upload_id": upload_id,
    }
    if document is not None:
        _validate_exclusive_access(document, admicorp_id)
        publication = add_internal_document_version_from_warehouse_upload(
            document_id=document.id,
            warehouse_upload_id=upload_id,
            created_by_user_id=automation_id,
            version_label=version_label,
            change_notes=f"Actualización diaria de {label} {cutoff.isoformat()}",
            audit_metadata=metadata,
        )
    else:
        publication = publish_internal_document_from_warehouse_upload(
            warehouse_upload_id=upload_id,
            title=title,
            category_key="REPORTES",
            created_by_user_id=automation_id,
            description=f"Reporte automático diario, semanal y mensual de {label}.",
            document_type="REPORTE_OPERATIVO",
            is_sensitive=True,
            visibility_mode="CUSTOM",
            visibility_rules=[{
                "visibility_type": "USER",
                "user_id": admicorp_id,
                "can_view": True,
                "can_download": True,
            }],
            links=[{
                "entity_type": "GENERAL",
                "entity_key": metric.upper(),
                "link_role": "OPERACION",
                "label": label.title(),
                "is_primary": True,
            }],
            publish_now=True,
            version_label=version_label,
            audit_metadata=metadata,
        )
    return {
        "metric": metric,
        "warehouse_upload_id": upload_id,
        "publication": publication,
    }


def run_job(*, business_date: date) -> dict[str, Any]:
    """Retry-safe: Warehouse hash reuse and document versions are idempotent."""
    automation_id, admicorp_id = _resolve_users()
    results = []
    for metric in METRICS:
        results.append(
            _publish_one(
                metric=metric,
                cutoff=business_date,
                automation_id=automation_id,
                admicorp_id=admicorp_id,
            )
        )
    return {"business_date": business_date.isoformat(), "reports": results}
