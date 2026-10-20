"""Read-only preflight for a future Gasca KPI Desempeño batch refresh.

This is NOT a runner, a publisher, a Gasca download or an authorization token.
It compares an explicitly selected Warehouse batch against CURRENT canonical
snapshots and validates the actual stored XLSX bytes through the M3-B audit.

An external trusted acquisition step must independently prove which files are
the latest official Gasca files. That capability is not implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hmac
import re
from typing import Mapping

from app.extensions import db
from app.models.warehouse import KpiDesempenoSnapshotORM, WarehouseUploadORM
from app.warehouse.services import kpi_desempeno_m3b_provenance_audit as provenance


ALREADY_CURRENT = "ALREADY_CURRENT"
CHANGES_DETECTED = "CHANGES_DETECTED"


class M3CPreflightError(ValueError):
    """Block: invalid source mapping, stale canonical state or unverified data."""


@dataclass(frozen=True)
class M3CPreflightDay:
    business_date: date
    canonical_snapshot_id: int
    selected_snapshot_id: int
    selected_upload_id: int
    verified_sha256: str
    needs_update: bool


@dataclass(frozen=True)
class M3CPreflightResult:
    status: str
    days_verified: int
    changed_dates: tuple[date, ...]
    days: tuple[M3CPreflightDay, ...]
    mtd_declines: int
    # This module cannot prove an external Gasca acquisition or authorize writes.
    external_origin_verified: bool = False
    execution_allowed: bool = False


def _validate_scope(
    selected: Mapping[date, int],
    canonical: Mapping[date, int],
    hashes: Mapping[date, str],
) -> tuple[date, ...]:
    if not selected or set(selected) != set(canonical) or set(selected) != set(hashes):
        raise M3CPreflightError("Incomplete candidate/canonical/hash date maps")
    days = tuple(sorted(selected))
    if len(days) < 2 or type(days[0]) is not date or days[0].day != 1:
        raise M3CPreflightError("Batch must begin at day 1 and include at least 2 days")
    for index, day in enumerate(days):
        if (
            type(day) is not date
            or day != days[0] + timedelta(days=index)
            or (day.year, day.month) != (days[0].year, days[0].month)
        ):
            raise M3CPreflightError("Batch dates must be contiguous in a single month")
        ids = (selected[day], canonical[day])
        if any(type(value) is not int or value <= 0 for value in ids):
            raise M3CPreflightError(f"{day}: invalid snapshot IDs")
        digest = hashes[day]
        if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise M3CPreflightError(f"{day}: invalid expected SHA-256")
    return days


def preflight_kpi_desempeno_existing_batch(
    *,
    selected_snapshot_ids: Mapping[date, int],
    expected_canonical_snapshot_ids: Mapping[date, int],
    expected_sha256_by_day: Mapping[date, str],
    expected_branch_count: int = 26,
) -> M3CPreflightResult:
    """Audit and compare an explicit month-to-date batch; never mutate storage.

    The expected SHA hashes must come from a trusted internal acquisition
    manifest, not directly from client-supplied claims. Even then, this result
    does NOT prove official Gasca origin or that the files are latest.

    ALREADY_CURRENT means *these exact verified Warehouse snapshots* are
    canonical, not a statement about the provider's newest available data.

    The result is an ephemeral diagnostic: concurrent writes after the final
    read remain possible. A future executor must re-check all canonical IDs
    under its own transaction/lock; it must never treat this as permission.
    """
    if type(expected_branch_count) is not int or expected_branch_count <= 0:
        raise M3CPreflightError("Invalid expected branch count")

    days = _validate_scope(
        selected_snapshot_ids,
        expected_canonical_snapshot_ids,
        expected_sha256_by_day,
    )

    # This verifies each canonical/candidate snapshot, parses the stored XLSX,
    # checks its SHA-256 and row values, and detects source MTD revisions.
    try:
        audit = provenance.audit_kpi_desempeno_m3b_provenance(
            candidate_snapshot_ids=selected_snapshot_ids,
            canonical_snapshot_ids=expected_canonical_snapshot_ids,
            expected_branch_count=expected_branch_count,
        )
    except provenance.M3BProvenanceError as exc:
        raise M3CPreflightError(f"Warehouse source audit failed: {exc}") from exc

    if (
        audit.publication_authorized
        or audit.days_verified != len(days)
        or audit.branches_per_day != expected_branch_count
        or audit.status not in {"SOURCE_VERIFIED", "SOURCE_VERIFIED_WITH_MTD_REVISIONS"}
    ):
        raise M3CPreflightError("Unexpected Warehouse audit result")

    details = []
    for day in days:
        snapshot_id = selected_snapshot_ids[day]
        snapshot = db.session.get(KpiDesempenoSnapshotORM, snapshot_id)
        if snapshot is None or snapshot.business_date != day:
            raise M3CPreflightError(f"{day}: selected snapshot changed")
        upload = db.session.get(WarehouseUploadORM, snapshot.warehouse_upload_id)
        if upload is None:
            raise M3CPreflightError(f"{day}: verified upload disappeared")
        digest = str(upload.file_hash_sha256).lower()
        if not hmac.compare_digest(digest, expected_sha256_by_day[day]):
            raise M3CPreflightError(f"{day}: expected Gasca SHA differs from Warehouse")

        # Detect a concurrent canonical replacement during this read. This is
        # only a read-time check, not a lock or a durable execution approval.
        if provenance._canonical_ids(day) != (expected_canonical_snapshot_ids[day],):
            raise M3CPreflightError(f"{day}: canonical changed during preflight")

        details.append(M3CPreflightDay(
            business_date=day,
            canonical_snapshot_id=expected_canonical_snapshot_ids[day],
            selected_snapshot_id=snapshot_id,
            selected_upload_id=upload.id,
            verified_sha256=digest,
            needs_update=snapshot_id != expected_canonical_snapshot_ids[day],
        ))

    updated = tuple(item.business_date for item in details if item.needs_update)
    return M3CPreflightResult(
        status=CHANGES_DETECTED if updated else ALREADY_CURRENT,
        days_verified=len(details),
        changed_dates=updated,
        days=tuple(details),
        mtd_declines=len(audit.declines),
    )
