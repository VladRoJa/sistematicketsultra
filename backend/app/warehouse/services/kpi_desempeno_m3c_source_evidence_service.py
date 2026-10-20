"""Read-only M3-C classification of Warehouse KPI Desempeño acquisition evidence.

Important: Warehouse evidence proves a document was recorded by Suite Ultra,
not that it is the provider's latest publication. Legacy KPI jobs often return
None, then find a recent file on disk. Neither mtime nor upload ID establish
provider freshness.

This module never approves processing, calls Gasca or updates any row.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.extensions import db
from app.models.warehouse import WarehouseAuditLogORM, WarehouseUploadORM


DISK_FALLBACK_UNVERIFIED = "DISK_FALLBACK_UNVERIFIED"
DIRECT_ARTIFACT_UNVERIFIED = "DIRECT_ARTIFACT_UNVERIFIED"
UNKNOWN_ACQUISITION_UNVERIFIED = "UNKNOWN_ACQUISITION_UNVERIFIED"


class M3CSourceEvidenceError(ValueError):
    """Invalid or absent Warehouse evidence for the selected KPI upload."""


@dataclass(frozen=True, slots=True)
class M3CSourceEvidence:
    warehouse_upload_id: int
    business_date: date
    status: str
    acquisition_method: str
    # All these evidence methods can be spoofed in historic documents or
    # originate in a local file. A separate trusted provider check is needed.
    provider_latest_verified: bool = False
    execution_allowed: bool = False


def classify_kpi_desempeno_warehouse_evidence(
    *, warehouse_upload_id: int, business_date: date,
) -> M3CSourceEvidence:
    """Classify stored internal provenance without trusting it as Gasca's latest.

    The UPLOAD audit event must be attributed to the upload's recorded actor.
    Source metadata is only a hint about the *internal acquisition method*.
    It does not independently attest a successful authenticated live report
    request nor supply a provider revision number.
    """
    if (
        type(warehouse_upload_id) is not int or warehouse_upload_id <= 0
        or type(business_date) is not date
    ):
        raise M3CSourceEvidenceError("Expected positive upload ID and exact date")

    upload = db.session.get(WarehouseUploadORM, warehouse_upload_id)
    if (
        upload is None
        or upload.status != "ACTIVE"
        or upload.source_file_deleted_at is not None
        or upload.period_type != "diario"
        or upload.cutoff_date != business_date
        or upload.report_type is None
        or upload.report_type.key != "kpi_desempeno"
    ):
        raise M3CSourceEvidenceError("Upload missing or not an active KPI daily source")

    record = WarehouseAuditLogORM.query.filter_by(
        upload_id=upload.id,
        action="UPLOAD",
        performed_by_user_id=upload.uploaded_by_user_id,
    ).first()
    if record is None:
        raise M3CSourceEvidenceError("Missing original Warehouse UPLOAD audit")

    details = record.details if isinstance(record.details, dict) else {}
    if (
        details.get("upload_origin") != "internal_pipeline"
        or details.get("source_key") != "gasca"
    ):
        raise M3CSourceEvidenceError("Upload is not recorded as internal Gasca acquisition")

    # Other extractor-supplied fields (including made-up provider revisions,
    # booleans and timestamps) are intentionally ignored: not proof of
    # provider freshness. bridge_source is only a diagnostic of code path.
    method = details.get("bridge_source")
    if method == "recent_disk_scan":
        status = DISK_FALLBACK_UNVERIFIED
    elif method in {"direct_path_result", "dict_result", "single_report_runner"}:
        status = DIRECT_ARTIFACT_UNVERIFIED
    else:
        status = UNKNOWN_ACQUISITION_UNVERIFIED

    return M3CSourceEvidence(
        warehouse_upload_id=upload.id,
        business_date=business_date,
        status=status,
        acquisition_method=method if isinstance(method, str) else "unknown",
    )
