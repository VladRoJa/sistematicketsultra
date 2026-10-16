"""M3-A: isolated, explicit NON-CANONICAL KPI Desempeno staging.

Not registered as a job, endpoint or normal ingestion path. Never runs Track.
The existing repository owns the INSERT/COMMIT; its supplied resolver is
fail-closed and cannot promote or replace the canonical snapshot.
"""
from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from typing import Any, Mapping

import pandas as pd
from flask import current_app

from app.extensions import db
from app.models.warehouse import (
    KpiDesempenoSnapshotORM,
    WarehouseUploadORM,
)
from app.warehouse.services.kpi_desempeno_parser import (
    EXPECTED_KPI_DESEMPENO_COLUMNS,
    KpiDesempenoParseResult,
    parse_kpi_desempeno_xlsx,
)
from app.warehouse.services.kpi_desempeno_repository import (
    persist_kpi_desempeno_snapshot,
)
from app.warehouse.services.kpi_desempeno_semantic_diff import (
    DIFFERENCES_DETECTED,
    KPI_METRIC_FIELDS,
    compare_kpi_desempeno_parsed,
)


class KpiDesempenoStagingError(ValueError):
    """Refuse staging rather than changing a canonical KPI or Track."""


def _business_date(value: date | str) -> date:
    if isinstance(value, datetime):
        raise KpiDesempenoStagingError("business_date must not be datetime")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise KpiDesempenoStagingError("business_date must be YYYY-MM-DD")


def _verified_bytes(upload: WarehouseUploadORM, *, expected_date: date) -> bytes:
    if upload.report_type is None or upload.report_type.key != "kpi_desempeno":
        raise KpiDesempenoStagingError("Warehouse upload is not KPI Desempeno")
    if upload.period_type != "diario" or upload.cutoff_date != expected_date:
        raise KpiDesempenoStagingError("Upload cutoff_date/period_type mismatch")
    if upload.status != "ACTIVE" or upload.source_file_deleted_at is not None:
        raise KpiDesempenoStagingError("Warehouse upload is not available")
    if not upload.stored_filename or not upload.stored_path:
        raise KpiDesempenoStagingError("Warehouse upload has no stored artifact")

    root = Path(current_app.root_path).parent.parent.resolve()
    path = (root / upload.stored_path / upload.stored_filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise KpiDesempenoStagingError("Warehouse artifact missing/outside storage")
    content = path.read_bytes()
    if (
        len(content) != upload.file_size_bytes
        or sha256(content).hexdigest().lower() != str(upload.file_hash_sha256).lower()
    ):
        raise KpiDesempenoStagingError("Warehouse artifact size/SHA-256 mismatch")
    return content


def _validate_embedded_date(payload: bytes, expected: date) -> None:
    """When an XLSX metadata tab exists, its business_date must agree.

    Files without this optional tab still require Warehouse cutoff_date.
    """
    with pd.ExcelFile(BytesIO(payload)) as book:
        metadata = next((s for s in book.sheet_names if s.lower() == "metadata"), None)
        if metadata is None:
            return
        values = pd.read_excel(book, sheet_name=metadata)
    if not {"key", "value"}.issubset(values.columns):
        raise KpiDesempenoStagingError("Malformed KPI metadata worksheet")
    rows = values.loc[
        values["key"].astype(str).str.strip().str.lower() == "business_date",
        "value",
    ]
    if len(rows) != 1:
        raise KpiDesempenoStagingError("KPI metadata business_date missing/duplicate")
    raw = rows.iloc[0]
    embedded_date = raw.date() if isinstance(raw, datetime) else _business_date(str(raw))
    if embedded_date != expected:
        raise KpiDesempenoStagingError("KPI XLSX business_date mismatch")


# Only these layouts are authorized. The date in the provider title is the
# *business* date, not the date when the XLSX was downloaded.
_GASCA_TITLE = re.compile(r"^KPIs Desempeño \(Corte: (\d{2}/\d{2}/\d{4})\)$")


def _normalize_kpi_layout_in_memory(payload: bytes, *, expected_date: date) -> bytes:
    """Adapt Gasca's one-title-row layout without changing stored XLSX bytes.

    The ordinary layout passes through unchanged. When A1 is the exact
    business-date title and row 2 is the exact nine-column header, return a
    separate in-memory XLSX understood by the existing parser/M1 comparator.
    """
    try:
        with pd.ExcelFile(BytesIO(payload)) as book:
            sheet = next(
                (name for name in book.sheet_names if name.strip().lower() == "data"),
                book.sheet_names[0],
            )
            raw = pd.read_excel(book, sheet_name=sheet, header=None)
    except Exception as exc:
        raise KpiDesempenoStagingError("Unreadable KPI XLSX layout") from exc

    def header_at(index: int) -> tuple[str, ...]:
        return tuple(
            "" if pd.isna(value) else str(value).strip()
            for value in raw.iloc[index].tolist()
        )

    if raw.shape[1] != len(EXPECTED_KPI_DESEMPENO_COLUMNS) or raw.empty:
        raise KpiDesempenoStagingError("Unexpected KPI column count or empty worksheet")

    header_positions = [
        index for index in range(len(raw))
        if header_at(index) == EXPECTED_KPI_DESEMPENO_COLUMNS
    ]
    if header_positions == [0]:
        return payload
    if header_positions != [1]:
        raise KpiDesempenoStagingError("Ambiguous or unexpected KPI headers")

    first_row = raw.iloc[0].tolist()
    if not isinstance(first_row[0], str) or any(
        not pd.isna(value) for value in first_row[1:]
    ):
        raise KpiDesempenoStagingError("Unexpected KPI title row")

    match = _GASCA_TITLE.fullmatch(first_row[0].strip())
    if match is None:
        raise KpiDesempenoStagingError("Unrecognized KPI business-date title")
    try:
        title_date = datetime.strptime(match.group(1), "%d/%m/%Y").date()
    except ValueError as exc:
        raise KpiDesempenoStagingError("Invalid KPI title business date") from exc
    if title_date != expected_date:
        raise KpiDesempenoStagingError("KPI title business_date mismatch")

    # Recreate ONLY the parsed view. The verified payload, source file,
    # Warehouse upload hash, and original workbook are never changed.
    data = raw.iloc[2:].copy()
    data.columns = EXPECTED_KPI_DESEMPENO_COLUMNS
    result = BytesIO()
    with pd.ExcelWriter(result, engine="openpyxl") as writer:
        data.to_excel(writer, sheet_name="data", index=False)
    return result.getvalue()


def _validate_integer_cells(payload: bytes) -> None:
    """Guard against parser's legacy int(float(value)) truncation."""
    with pd.ExcelFile(BytesIO(payload)) as book:
        sheet = next((s for s in book.sheet_names if s.strip().lower() == "data"), book.sheet_names[0])
        df = pd.read_excel(book, sheet_name=sheet)
    if tuple(str(c).strip() for c in df.columns) != EXPECTED_KPI_DESEMPENO_COLUMNS:
        raise KpiDesempenoStagingError("Unexpected KPI Excel header")
    integral_columns = EXPECTED_KPI_DESEMPENO_COLUMNS[1:8]
    for _, row in df.iterrows():
        name = str(row["Sucursal"]).strip().lower().replace(" ", "")
        if name in {"totales:", "totales", "nan", "none", ""}:
            continue
        for col in integral_columns:
            value = row[col]
            try:
                number = float(value)
            except (TypeError, ValueError):
                # Canonical parser will reject malformed content.
                continue
            if pd.notna(value) and number != int(number):
                raise KpiDesempenoStagingError(
                    f"Fractional value in integer KPI column {col!r}, branch {row['Sucursal']!r}"
                )


def _read_parsed(upload: WarehouseUploadORM, *, expected_date: date) -> KpiDesempenoParseResult:
    payload = _verified_bytes(upload, expected_date=expected_date)
    _validate_embedded_date(payload, expected_date)
    parsed_view = _normalize_kpi_layout_in_memory(payload, expected_date=expected_date)
    _validate_integer_cells(parsed_view)
    return parse_kpi_desempeno_xlsx(file_bytes=parsed_view)


def stage_kpi_desempeno_upload(
    *,
    warehouse_upload_id: int,
    canonical_snapshot_id: int,
    business_date: date | str,
    sucursal_aliases: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Stage an already stored Warehouse upload. Never creates an upload.

    Requires an explicit *current* canonical baseline, a distinct upload, and
    M1-approved branch/metric differences. No routes/schedulers invoke it.
    The callback rechecks the canonical identity inside the repository.
    """
    day = _business_date(business_date)
    if (
        type(warehouse_upload_id) is not int or warehouse_upload_id <= 0
        or type(canonical_snapshot_id) is not int or canonical_snapshot_id <= 0
    ):
        raise KpiDesempenoStagingError("Positive upload and baseline IDs required")
    if sucursal_aliases:
        # M3-A has no approved branch-renaming scope. Do not stage with an
        # inferred or externally supplied alias graph.
        raise KpiDesempenoStagingError("M3-A does not permit branch aliases")

    baseline = db.session.get(KpiDesempenoSnapshotORM, canonical_snapshot_id)
    if (
        baseline is None
        or baseline.business_date != day
        or baseline.snapshot_kind != "daily"
        or baseline.report_type_key != "kpi_desempeno"
        or not baseline.is_canonical
    ):
        raise KpiDesempenoStagingError("Canonical baseline identity mismatch")
    current = KpiDesempenoSnapshotORM.query.filter_by(
        business_date=day, snapshot_kind="daily", is_canonical=True,
    ).all()
    if len(current) != 1 or current[0].id != baseline.id:
        raise KpiDesempenoStagingError("Canonical baseline changed or ambiguous")

    upload = db.session.get(WarehouseUploadORM, warehouse_upload_id)
    baseline_upload = db.session.get(WarehouseUploadORM, baseline.warehouse_upload_id)
    if upload is None or baseline_upload is None:
        raise KpiDesempenoStagingError("Warehouse upload missing")
    if upload.id == baseline_upload.id:
        raise KpiDesempenoStagingError("Candidate must use a distinct upload")
    previous = _read_parsed(baseline_upload, expected_date=day)
    candidate = _read_parsed(upload, expected_date=day)
    if previous.row_count != baseline.row_count_valid:
        raise KpiDesempenoStagingError("Baseline rows differ from snapshot header")

    diff = compare_kpi_desempeno_parsed(
        previous=previous, current=candidate, business_date=day,
    )
    if (
        diff.status != DIFFERENCES_DETECTED
        or diff.validation_errors
        or diff.requires_identity_review
        or diff.previous_row_count != diff.current_row_count
    ):
        raise KpiDesempenoStagingError(
            f"M1 comparison is not stageable: {diff.status}; "
            f"identity_review={diff.requires_identity_review}; errors={diff.validation_errors}"
        )

    already = KpiDesempenoSnapshotORM.query.filter_by(
        warehouse_upload_id=upload.id
    ).one_or_none()
    if already is not None:
        if already.is_canonical or already.business_date != day or already.snapshot_kind != "daily":
            raise KpiDesempenoStagingError("Existing snapshot is not a matching staged candidate")
        return {
            "status": "already_staged", "was_idempotent": True,
            "snapshot_id": already.id, "warehouse_upload_id": upload.id,
            "canonical_snapshot_id": baseline.id, "business_date": day.isoformat(),
            "is_canonical": False, "changed_branches": len(diff.differences),
            "changed_fields": sum(len(entry.fields) for entry in diff.differences),
        }

    def stage_only_canonicality_resolver(*, existing_canonical_snapshot, **_kwargs):
        if (
            existing_canonical_snapshot is None
            or existing_canonical_snapshot.id != canonical_snapshot_id
            or not existing_canonical_snapshot.is_canonical
        ):
            raise KpiDesempenoStagingError("Canonical baseline moved while staging")
        return {
            "is_canonical": False,
            "replace_existing_canonical": False,
            "reason": "m3a_explicit_noncanonical_staging",
        }

    result = persist_kpi_desempeno_snapshot(
        warehouse_upload_id=upload.id,
        report_type_key="kpi_desempeno",
        business_date=day,
        captured_at=upload.created_at,
        snapshot_kind="daily",
        parsed_snapshot=candidate,
        canonicality_resolver=stage_only_canonicality_resolver,
    )
    if result["is_canonical"]:
        raise KpiDesempenoStagingError("Staging was unexpectedly promoted")
    if result.get("was_idempotent") and result.get("status") == "already_ingested":
        # Repository's concurrent-upload fallback must not silently authorize
        # a canonical or unrelated snapshot.
        concurrent = KpiDesempenoSnapshotORM.query.filter_by(
            warehouse_upload_id=upload.id
        ).one()
        if concurrent.is_canonical or concurrent.business_date != day:
            raise KpiDesempenoStagingError("Concurrent upload has incompatible snapshot")
    return {
        "status": "already_staged" if result["was_idempotent"] else "staged",
        "was_idempotent": bool(result["was_idempotent"]),
        "snapshot_id": result["snapshot_id"],
        "warehouse_upload_id": upload.id,
        "canonical_snapshot_id": baseline.id,
        "business_date": day.isoformat(),
        "is_canonical": False,
        "changed_branches": len(diff.differences),
        "changed_fields": sum(len(entry.fields) for entry in diff.differences),
    }
