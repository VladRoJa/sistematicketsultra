"""Trusted *read-only* bridge from verified Gasca Warehouse files to M3-B.

Caller supplies explicit snapshot IDs, not claims or approved booleans.
This function performs a fresh Warehouse audit before classifying negative MTD
deltas. It cannot publish snapshots, change canonicality or rebuild Track.
Only authenticated backend orchestration may invoke this path.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Mapping

from app.warehouse.services import kpi_desempeno_m3b_provenance_audit as provenance
from app.warehouse.services.kpi_desempeno_m3b_continuity_plan import (
    BLOCKED,
    KPI_TO_TRACK_F3,
    M3BContinuityIssue,
    M3BImpactPlan,
    MTD_TRACK_FIELDS,
    READY_FOR_PROCESSING,
    _date,
    _plan_kpi_desempeno_mtd_impact,
)
from app.warehouse.services.kpi_desempeno_semantic_diff import (
    DIFFERENCES_DETECTED,
    KpiDesempenoSemanticDiffResult,
)


def _f3_changed_fields(
    before: provenance.VerifiedKpiSource,
    after: provenance.VerifiedKpiSource,
) -> dict[tuple[str, str], tuple[int, int]]:
    if before.values.keys() != after.values.keys():
        raise provenance.M3BProvenanceError("Verified branch identities changed")
    indexed = {}
    for branch in before.values:
        previous, current = before.values[branch], after.values[branch]
        for index, metric in enumerate((
            "reactivaciones_real_mtd", "bajas_reales_mtd", "usuarios_activos_actual",
        )):
            if previous[index] != current[index]:
                indexed[(branch, metric)] = (previous[index], current[index])
    return indexed


def _f3_diff_fields(
    diff: KpiDesempenoSemanticDiffResult,
) -> dict[tuple[str, str], tuple[int, int]]:
    observed = {}
    for branch in diff.differences:
        for field in branch.fields:
            metric = KPI_TO_TRACK_F3.get(field.field)
            if metric is None:
                continue
            key = (branch.branch_key, metric)
            if key in observed or any(
                type(value) not in (int, float)
                or value < 0 or int(value) != value
                for value in (field.previous, field.current)
            ):
                raise provenance.M3BProvenanceError("Invalid or duplicate F3 M1 difference")
            observed[key] = (int(field.previous), int(field.current))
    return observed


def _mtd_values(source: provenance.VerifiedKpiSource) -> dict[str, dict[str, int]]:
    return {
        branch: {
            "reactivaciones_real_mtd": values[0],
            "bajas_reales_mtd": values[1],
        }
        for branch, values in source.values.items()
    }


def plan_kpi_desempeno_verified_source_impact(
    *,
    business_date: date | str,
    diff: KpiDesempenoSemanticDiffResult,
    candidate_snapshot_ids: Mapping[date, int],
    canonical_snapshot_ids: Mapping[date, int],
    expected_branch_count: int = 26,
) -> M3BImpactPlan:
    """Produce a fail-closed plan only after reading authenticated Warehouse data.

    The *entire* selected month-to-date series is audited first. A decline may
    cease being a blocker only if the exact branch/date/metric/value pair also
    occurs among the auditor's verified candidate-source declines. All other
    continuity, identity and M1 validation blockers remain fatal.

    READY_FOR_PROCESSING means preflight classification only, NEVER that any
    promotion, DB transaction, Track rebuild or scheduler run occurred.
    """
    day = _date(business_date)
    audit = provenance.audit_kpi_desempeno_m3b_provenance(
        candidate_snapshot_ids=candidate_snapshot_ids,
        canonical_snapshot_ids=canonical_snapshot_ids,
        expected_branch_count=expected_branch_count,
    )
    if audit.publication_authorized or audit.status not in {
        "SOURCE_VERIFIED", "SOURCE_VERIFIED_WITH_MTD_REVISIONS",
    }:
        raise provenance.M3BProvenanceError("Unexpected provenance-audit outcome")
    if day not in candidate_snapshot_ids or diff.status != DIFFERENCES_DETECTED:
        raise provenance.M3BProvenanceError("Business date has no verified source changes")
    if diff.business_date != day.isoformat() or diff.validation_errors or diff.requires_identity_review:
        raise provenance.M3BProvenanceError("Unsafe M1 semantic difference")

    def load(source_day: date, *, canonical: bool):
        source_id = (
            canonical_snapshot_ids[source_day] if canonical
            else candidate_snapshot_ids[source_day]
        )
        is_canonical = canonical or source_id == canonical_snapshot_ids[source_day]
        return provenance._load_verified_source(
            day=source_day,
            snapshot_id=source_id,
            expected_canonical=is_canonical,
            expected_count=expected_branch_count,
        )

    original = load(day, canonical=True)
    latest = load(day, canonical=False)
    expected_f3 = _f3_changed_fields(original, latest)
    actual_f3 = _f3_diff_fields(diff)
    if expected_f3 != actual_f3:
        raise provenance.M3BProvenanceError(
            "M1 F3 changes do not match verified Gasca source values"
        )

    observed = {day: _mtd_values(original)}
    for neighbor in (day - timedelta(days=1), day + timedelta(days=1)):
        if neighbor in candidate_snapshot_ids:
            observed[neighbor] = _mtd_values(load(neighbor, canonical=False))

    raw_plan = _plan_kpi_desempeno_mtd_impact(
        business_date=day, diff=diff, observed_mtd=observed,
        _verified_series_end=max(candidate_snapshot_ids),
    )

    verified_keys = {
        (d.earlier_date, d.later_date, d.branch_key, d.track_field,
         d.earlier, d.later)
        for d in audit.declines
        if d.track_field in MTD_TRACK_FIELDS
    }
    blockers = []
    accepted_revisions = []
    for issue in raw_plan.blocking_issues:
        key = (
            issue.earlier_date, issue.later_date, issue.branch_key,
            issue.track_mtd_field, issue.earlier, issue.later,
        )
        if issue.code == "MTD_DECREASE" and key in verified_keys:
            accepted_revisions.append(replace(
                issue, code="MTD_VERIFIED_SOURCE_REVISION",
            ))
        else:
            blockers.append(issue)

    return replace(
        raw_plan,
        status=BLOCKED if blockers else READY_FOR_PROCESSING,
        blocking_issues=tuple(blockers),
        verified_source_revisions=tuple(accepted_revisions),
    )
