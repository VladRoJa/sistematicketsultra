"""M3-B: read-only, fail-closed Warehouse provenance audit for KPI MTD series.

This service verifies stored files and structured F3 source cells, and compares
consecutive business dates. It NEVER approves a revision, writes to Warehouse,
changes canonicality, or runs Track. KPI-specific approval storage does not
exist in this scope; documented declines remain awaiting human authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Mapping
import unicodedata

from app.extensions import db
from app.models.warehouse import (
    KpiDesempenoSnapshotORM,
    KpiDesempenoSnapshotRowORM,
    WarehouseAuditLogORM,
    WarehouseUploadORM,
)
from app.warehouse.services.kpi_desempeno_staging_service import _read_parsed


class M3BProvenanceError(ValueError):
    """Unverifiable provenance: fail closed without a report."""


@dataclass(frozen=True)
class VerifiedKpiSource:
    day: date
    snapshot_id: int
    upload_id: int
    file_hash_sha256: str
    is_canonical: bool
    # branch_key -> (reactivaciones MTD, bajas MTD, socios activos)
    values: dict[str, tuple[int, int, int]]


@dataclass(frozen=True)
class M3BSourceDecline:
    earlier_date: date
    later_date: date
    branch_key: str
    track_field: str
    earlier: int
    later: int
    delta: int
    earlier_snapshot_id: int
    later_snapshot_id: int
    earlier_upload_id: int
    later_upload_id: int
    earlier_sha256: str
    later_sha256: str
    review_status: str = "FUENTE_VERIFICADA_REVISION_MTD"


@dataclass(frozen=True)
class M3BProvenanceReport:
    status: str
    days_verified: int
    branches_per_day: int
    declines: tuple[M3BSourceDecline, ...]
    shared_declines: int
    new_declines: int
    removed_declines: int
    publication_authorized: bool = False


def _branch_key(value: str) -> str:
    if not isinstance(value, str):
        raise M3BProvenanceError("Non-text branch identity")
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _source_values(rows, *, label: str, expected_count: int, parsed: bool) -> dict[str, tuple[int, int, int]]:
    values = {}
    for row in rows:
        key = _branch_key(row.sucursal_nombre if parsed else row.sucursal)
        if not key or key in values:
            raise M3BProvenanceError(f"{label}: missing or repeated branch")
        v = (row.reactivaciones, row.bajas, row.socios_activos_del_mes)
        if any(type(n) is not int or n < 0 for n in v):
            raise M3BProvenanceError(f"{label}: invalid F3 integer")
        values[key] = v
    if len(values) != expected_count:
        raise M3BProvenanceError(f"{label}: expected {expected_count} branches, got {len(values)}")
    return values


def _db_get(model, object_id):
    return db.session.get(model, object_id)


def _upload_has_audit(upload: WarehouseUploadORM) -> bool:
    return WarehouseAuditLogORM.query.filter_by(
        upload_id=upload.id, action="UPLOAD",
        performed_by_user_id=upload.uploaded_by_user_id,
    ).first() is not None


def _stored_rows(snapshot_id: int):
    return KpiDesempenoSnapshotRowORM.query.filter_by(snapshot_id=snapshot_id).all()


def _canonical_ids(day: date) -> tuple[int, ...]:
    return tuple(
        s.id for s in KpiDesempenoSnapshotORM.query.filter_by(
            business_date=day, snapshot_kind="daily", is_canonical=True,
        ).all()
    )


def _load_verified_source(
    *,
    day: date,
    snapshot_id: int,
    expected_canonical: bool,
    expected_count: int,
) -> VerifiedKpiSource:
    snapshot = _db_get(KpiDesempenoSnapshotORM, snapshot_id)
    if (
        snapshot is None or snapshot.business_date != day
        or snapshot.snapshot_kind != "daily"
        or snapshot.report_type_key != "kpi_desempeno"
        or snapshot.is_canonical is not expected_canonical
        or snapshot.row_count_valid != expected_count
        or snapshot.row_count_rejected != 0
    ):
        raise M3BProvenanceError(f"{day}: snapshot identity/count/canonicality mismatch")

    upload = _db_get(WarehouseUploadORM, snapshot.warehouse_upload_id)
    if upload is None:
        raise M3BProvenanceError(f"{day}: missing upload")

    # An UPLOAD event proves Warehouse recorded this file and the named actor.
    # It does NOT prove a Gasca revision was approved by that actor.
    if not _upload_has_audit(upload):
        raise M3BProvenanceError(f"{day}: missing upload audit event")

    # Reuses M3-A byte-size/SHA, path, report type, cutoff, embedded-date,
    # layout and cell-integrality checks. No write or re-ingestion.
    parsed = _read_parsed(upload, expected_date=day)
    if parsed.row_count != expected_count:
        raise M3BProvenanceError(f"{day}: raw source row count mismatch")
    raw = _source_values(
        parsed.rows, label=f"{day}/XLSX", expected_count=expected_count, parsed=True,
    )
    saved_rows = _stored_rows(snapshot_id)
    saved = _source_values(
        saved_rows, label=f"{day}/DB", expected_count=expected_count, parsed=False,
    )
    if raw != saved:
        raise M3BProvenanceError(f"{day}: structured F3 rows differ from verified source")
    return VerifiedKpiSource(
        day=day, snapshot_id=snapshot_id, upload_id=upload.id,
        file_hash_sha256=upload.file_hash_sha256.lower(),
        is_canonical=expected_canonical, values=raw,
    )


def _declines(
    series: Mapping[date, VerifiedKpiSource],
) -> dict[tuple[date, str, str], M3BSourceDecline]:
    days = sorted(series)
    found = {}
    for yesterday, today in zip(days, days[1:]):
        a, b = series[yesterday], series[today]
        for branch in sorted(a.values):
            for field, index in (("reactivaciones_real_mtd", 0), ("bajas_reales_mtd", 1)):
                before, after = a.values[branch][index], b.values[branch][index]
                if after >= before:
                    continue
                key = (today, branch, field)
                found[key] = M3BSourceDecline(
                    earlier_date=yesterday, later_date=today,
                    branch_key=branch, track_field=field,
                    earlier=before, later=after, delta=after-before,
                    earlier_snapshot_id=a.snapshot_id,
                    later_snapshot_id=b.snapshot_id,
                    earlier_upload_id=a.upload_id,
                    later_upload_id=b.upload_id,
                    earlier_sha256=a.file_hash_sha256,
                    later_sha256=b.file_hash_sha256,
                )
    return found


def audit_kpi_desempeno_m3b_provenance(
    *,
    candidate_snapshot_ids: Mapping[date, int],
    canonical_snapshot_ids: Mapping[date, int],
    expected_branch_count: int = 26,
) -> M3BProvenanceReport:
    """Inspect contiguous month-to-date snapshots; never mutate DB or approval state.

    Use ONLY from a trusted internal context. IDs are explicit, not inferred from
    the latest snapshot. Same ID is permitted only for an unchanged canonical day.
    """
    if type(expected_branch_count) is not int or expected_branch_count <= 0:
        raise M3BProvenanceError("Invalid expected branch count")
    if not candidate_snapshot_ids or set(candidate_snapshot_ids) != set(canonical_snapshot_ids):
        raise M3BProvenanceError("Candidate and baseline dates differ")
    days = sorted(candidate_snapshot_ids)
    if (
        len(days) < 2 or any(type(day) is not date for day in days)
        or days[0].day != 1
        or any(
            day != days[0] + timedelta(days=i)
            or (day.year, day.month) != (days[0].year, days[0].month)
            for i, day in enumerate(days)
        )
    ):
        raise M3BProvenanceError("Series must be contiguous and within one business month")

    proposed, original = {}, {}
    for day in days:
        proposed_id, baseline_id = candidate_snapshot_ids[day], canonical_snapshot_ids[day]
        if (
            type(proposed_id) is not int or proposed_id <= 0
            or type(baseline_id) is not int or baseline_id <= 0
        ):
            raise M3BProvenanceError(f"{day}: invalid snapshot id")
        if _canonical_ids(day) != (baseline_id,):
            raise M3BProvenanceError(f"{day}: expected canonical has changed")
        original[day] = _load_verified_source(
            day=day, snapshot_id=baseline_id, expected_canonical=True,
            expected_count=expected_branch_count,
        )
        proposed[day] = (
            original[day] if proposed_id == baseline_id
            else _load_verified_source(
                day=day, snapshot_id=proposed_id, expected_canonical=False,
                expected_count=expected_branch_count,
            )
        )
        if original[day].values.keys() != proposed[day].values.keys():
            raise M3BProvenanceError(f"{day}: candidate branch identities differ from baseline")

    expected_branches = proposed[days[0]].values.keys()
    if any(s.values.keys() != expected_branches for s in proposed.values()):
        raise M3BProvenanceError("Roster differs across candidate dates")
    if any(s.values.keys() != expected_branches for s in original.values()):
        raise M3BProvenanceError("Roster differs across baseline dates")

    proposed_drops = _declines(proposed)
    baseline_drops = _declines(original)
    shared = proposed_drops.keys() & baseline_drops.keys()

    return M3BProvenanceReport(
        status="SOURCE_VERIFIED_WITH_MTD_REVISIONS" if proposed_drops else "SOURCE_VERIFIED",
        days_verified=len(days), branches_per_day=expected_branch_count,
        declines=tuple(proposed_drops[key] for key in sorted(proposed_drops)),
        shared_declines=len(shared),
        new_declines=len(proposed_drops.keys() - baseline_drops.keys()),
        removed_declines=len(baseline_drops.keys() - proposed_drops.keys()),
    )
