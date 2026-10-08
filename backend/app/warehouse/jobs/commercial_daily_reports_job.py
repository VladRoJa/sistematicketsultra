"""Publish closed-day commercial reports to ADMICORP in Corporate Cloud."""
from __future__ import annotations

import os
from datetime import date
from typing import Any

from app.internal_documents.services.internal_document_publication_service import (
    add_internal_document_version_from_warehouse_upload,
    publish_internal_document_from_warehouse_upload,
)
from app.models import (
    InternalDocumentORM,
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
    document = (
        InternalDocumentORM.query
        .filter(
            InternalDocumentORM.title == title,
            InternalDocumentORM.status != InternalDocumentStatus.ARCHIVED,
        )
        .order_by(InternalDocumentORM.id.asc())
        .first()
    )
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
            version_label=cutoff.isoformat(),
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
            version_label=cutoff.isoformat(),
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
