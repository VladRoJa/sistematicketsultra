"""M3-B phase 1: PURE impact and MTD-continuity planning, no DB access.

This module never reconstructs, stages, promotes, publishes, queries Warehouse,
or writes Track. Input provenance and branch identities must be verified by
the future authorized caller; synthetic tests exercise its deterministic contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
import re
from typing import Mapping

from app.warehouse.services.kpi_desempeno_semantic_diff import (
    DIFFERENCES_DETECTED,
    KPI_METRIC_FIELDS,
    KpiDesempenoSemanticDiffResult,
)

# Exactly three KPI columns feed Track F3. No other mart field may be projected.
KPI_TO_TRACK_F3 = {
    "socios_activos_del_mes": "usuarios_activos_actual",
    "reactivaciones": "reactivaciones_real_mtd",
    "bajas": "bajas_reales_mtd",
}
MTD_TRACK_FIELDS = frozenset({"reactivaciones_real_mtd", "bajas_reales_mtd"})
READY_FOR_REVIEW = "READY_FOR_REVIEW"
BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class M3BSnapshotFieldImpact:
    business_date: date
    branch_key: str
    kpi_field: str
    previous: int | float
    current: int | float


@dataclass(frozen=True, slots=True)
class M3BTrackFieldImpact:
    business_date: date
    branch_key: str
    track_field: str
    previous: int
    current: int


@dataclass(frozen=True, slots=True)
class M3BDerivedDailyImpact:
    business_date: date
    branch_key: str
    track_mtd_field: str


@dataclass(frozen=True, slots=True)
class M3BContinuityIssue:
    code: str
    branch_key: str
    track_mtd_field: str
    earlier_date: date | None = None
    later_date: date | None = None
    earlier: int | None = None
    later: int | None = None
    delta: int | None = None


@dataclass(frozen=True, slots=True)
class M3BSourceRevisionEvidence:
    """Attestation scoped to one *negative* MTD day-pair, not a waiver.

    The future trusted loader MUST verify upload IDs, SHA-256, source values,
    reviewer authorization and review_reference against Warehouse/audit data.
    This pure function only validates shape and matches exact values.
    """
    branch_key: str
    track_mtd_field: str
    earlier_date: date
    later_date: date
    earlier: int
    later: int
    earlier_upload_id: int
    later_upload_id: int
    earlier_sha256: str
    later_sha256: str
    reviewer_user_id: int
    review_reference: str


@dataclass(frozen=True, slots=True)
class M3BImpactPlan:
    status: str
    business_date: date
    changed_snapshot_fields: tuple[M3BSnapshotFieldImpact, ...]
    track_field_changes: tuple[M3BTrackFieldImpact, ...]
    continuity_days: tuple[date, ...]
    derived_delta_impacts: tuple[M3BDerivedDailyImpact, ...]
    blocking_issues: tuple[M3BContinuityIssue, ...]
    documented_decreases: tuple[M3BContinuityIssue, ...] = ()


def _date(value: date | str) -> date:
    if isinstance(value, datetime):
        raise ValueError("business_date requires date, not datetime")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    raise ValueError("business_date must be YYYY-MM-DD")


def _observed_value(
    observed: Mapping[date, Mapping[str, Mapping[str, int]]],
    day: date,
    branch: str,
    metric: str,
    *,
    issues: list[M3BContinuityIssue],
) -> int | None:
    day_values = observed.get(day)
    if day_values is None:
        issues.append(M3BContinuityIssue(
            "MISSING_DAY", branch, metric, earlier_date=day,
        ))
        return None
    branch_values = day_values.get(branch)
    if branch_values is None:
        issues.append(M3BContinuityIssue(
            "MISSING_BRANCH", branch, metric, earlier_date=day,
        ))
        return None
    value = branch_values.get(metric)
    if type(value) is not int or value < 0:
        issues.append(M3BContinuityIssue(
            "INVALID_MTD", branch, metric, earlier_date=day,
        ))
        return None
    return value


def _valid_revision_evidence(item: M3BSourceRevisionEvidence) -> bool:
    """Validate exact pair and metadata shape, NOT external provenance."""
    return (
        isinstance(item.branch_key, str)
        and bool(item.branch_key.strip())
        and item.branch_key == item.branch_key.strip()
        and isinstance(item.track_mtd_field, str)
        and item.track_mtd_field in MTD_TRACK_FIELDS
        and type(item.earlier_date) is date
        and type(item.later_date) is date
        and item.later_date == item.earlier_date + timedelta(days=1)
        and (item.earlier_date.year, item.earlier_date.month)
            == (item.later_date.year, item.later_date.month)
        and type(item.earlier) is int and type(item.later) is int
        and item.earlier > item.later >= 0
        and type(item.earlier_upload_id) is int and item.earlier_upload_id > 0
        and type(item.later_upload_id) is int and item.later_upload_id > 0
        and item.earlier_upload_id != item.later_upload_id
        and type(item.reviewer_user_id) is int and item.reviewer_user_id > 0
        and isinstance(item.review_reference, str)
        and 1 <= len(item.review_reference.strip()) <= 200
        and item.review_reference == item.review_reference.strip()
        and isinstance(item.earlier_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", item.earlier_sha256) is not None
        and isinstance(item.later_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", item.later_sha256) is not None
    )


def _revision_key(
    branch: str, metric: str, earlier_date: date, later_date: date,
    earlier: int, later: int,
) -> tuple[str, str, date, date, int, int]:
    return (branch, metric, earlier_date, later_date, earlier, later)


def plan_kpi_desempeno_mtd_impact(
    *,
    business_date: date | str,
    diff: KpiDesempenoSemanticDiffResult,
    observed_mtd: Mapping[date, Mapping[str, Mapping[str, int]]],
    source_revision_evidence: tuple[M3BSourceRevisionEvidence, ...] = (),
) -> M3BImpactPlan:
    """Compute exact impact cells and neighbor-day MTD checks, without IO.

    observed_mtd is indexed by M1's *exact normalized branch_key*, not by
    guessed aliases. No mutation of input maps, Track or Warehouse.

    Evidence is accepted only from a trusted caller that has independently
    checked the Warehouse artifacts and authorized review record. The planner
    never verifies cryptographic provenance by itself and never publishes.
    """
    day = _date(business_date)
    issues: list[M3BContinuityIssue] = []
    documented_decreases: list[M3BContinuityIssue] = []
    evidence_index: dict[
        tuple[str, str, date, date, int, int], M3BSourceRevisionEvidence
    ] = {}
    consumed_evidence: set[tuple[str, str, date, date, int, int]] = set()

    for item in source_revision_evidence:
        if not isinstance(item, M3BSourceRevisionEvidence) or not _valid_revision_evidence(item):
            issues.append(M3BContinuityIssue(
                "INVALID_SOURCE_REVISION_EVIDENCE",
                getattr(item, "branch_key", ""),
                getattr(item, "track_mtd_field", ""),
            ))
            continue
        key = _revision_key(
            item.branch_key, item.track_mtd_field, item.earlier_date,
            item.later_date, item.earlier, item.later,
        )
        if key in evidence_index:
            issues.append(M3BContinuityIssue(
                "DUPLICATE_SOURCE_REVISION_EVIDENCE",
                item.branch_key, item.track_mtd_field,
                item.earlier_date, item.later_date, item.earlier, item.later,
            ))
            continue
        evidence_index[key] = item

    def record_decrease(
        branch: str, metric: str, earlier_day: date, later_day: date,
        earlier: int, later: int,
    ) -> None:
        key = _revision_key(branch, metric, earlier_day, later_day, earlier, later)
        finding = M3BContinuityIssue(
            "MTD_SOURCE_REVISION_REVIEW" if key in evidence_index else "MTD_DECREASE",
            branch, metric, earlier_day, later_day, earlier, later,
            later - earlier,
        )
        if key in evidence_index:
            consumed_evidence.add(key)
            documented_decreases.append(finding)
        else:
            issues.append(finding)

    snapshot_impacts: list[M3BSnapshotFieldImpact] = []
    track_impacts: list[M3BTrackFieldImpact] = []
    changed_mtd: dict[tuple[str, str], tuple[int, int]] = {}
    seen_branches: set[str] = set()
    allowed_fields = frozenset(KPI_METRIC_FIELDS)

    if (
        diff.status != DIFFERENCES_DETECTED
        or diff.business_date != day.isoformat()
        or diff.validation_errors
        or diff.requires_identity_review
        or not diff.differences
    ):
        issues.append(M3BContinuityIssue("INVALID_M1_DIFF", "", ""))
    else:
        for branch in diff.differences:
            if (
                branch.kind != "CHANGED"
                or not branch.branch_key
                or branch.branch_key in seen_branches
                or not branch.fields
            ):
                issues.append(M3BContinuityIssue(
                    "INVALID_BRANCH_IDENTITY", branch.branch_key, ""
                ))
                continue
            seen_branches.add(branch.branch_key)
            seen_fields: set[str] = set()
            for field in branch.fields:
                if field.field not in allowed_fields or field.field in seen_fields:
                    issues.append(M3BContinuityIssue(
                        "INVALID_M1_FIELD", branch.branch_key, field.field
                    ))
                    continue
                seen_fields.add(field.field)
                # M1 may be supplied with already-structured differences.
                # Validate both sides independently before converting to int:
                # NaN/inf must never reach int() or the continuity checks.
                def valid_metric_value(value: object) -> bool:
                    if type(value) is int:
                        pass
                    elif type(value) is float and math.isfinite(value):
                        pass
                    else:
                        return False
                    if field.field != "alcance_meta":
                        return value >= 0 and int(value) == value
                    return True

                if (
                    not valid_metric_value(field.previous)
                    or not valid_metric_value(field.current)
                    or field.previous == field.current
                ):
                    issues.append(M3BContinuityIssue(
                        "INVALID_M1_FIELD", branch.branch_key, field.field
                    ))
                    continue

                snapshot_impacts.append(M3BSnapshotFieldImpact(
                    day, branch.branch_key, field.field,
                    field.previous, field.current,
                ))
                target = KPI_TO_TRACK_F3.get(field.field)
                if target is None:
                    continue
                track_impacts.append(M3BTrackFieldImpact(
                    day, branch.branch_key, target,
                    int(field.previous), int(field.current),
                ))
                if target in MTD_TRACK_FIELDS:
                    changed_mtd[(branch.branch_key, target)] = (
                        int(field.previous), int(field.current)
                    )

    continuity_days: set[date] = set()
    derived_impacts: list[M3BDerivedDailyImpact] = []

    for (branch, metric), (old, corrected) in sorted(changed_mtd.items()):
        prev_day, next_day = day - timedelta(days=1), day + timedelta(days=1)
        previous_is_same_month = (prev_day.year, prev_day.month) == (day.year, day.month)
        next_is_same_month = (next_day.year, next_day.month) == (day.year, day.month)

        continuity_days.add(day)
        if previous_is_same_month:
            continuity_days.add(prev_day)
        if next_is_same_month:
            continuity_days.add(next_day)

        current_old = _observed_value(
            observed_mtd, day, branch, metric, issues=issues
        )
        if current_old is not None and current_old != old:
            issues.append(M3BContinuityIssue(
                "BASELINE_MISMATCH", branch, metric, earlier_date=day,
                earlier=current_old, later=old, delta=old-current_old,
            ))

        prev_value = (
            _observed_value(observed_mtd, prev_day, branch, metric, issues=issues)
            if previous_is_same_month else None
        )
        next_value = (
            _observed_value(observed_mtd, next_day, branch, metric, issues=issues)
            if next_is_same_month else None
        )

        if previous_is_same_month and prev_value is not None and corrected < prev_value:
            record_decrease(branch, metric, prev_day, day, prev_value, corrected)
        if next_is_same_month and next_value is not None and next_value < corrected:
            record_decrease(branch, metric, day, next_day, corrected, next_value)

        derived_impacts.append(M3BDerivedDailyImpact(day, branch, metric))
        if next_is_same_month:
            derived_impacts.append(M3BDerivedDailyImpact(next_day, branch, metric))

    for key, item in evidence_index.items():
        if key not in consumed_evidence:
            issues.append(M3BContinuityIssue(
                "UNMATCHED_SOURCE_REVISION_EVIDENCE",
                item.branch_key, item.track_mtd_field,
                item.earlier_date, item.later_date, item.earlier, item.later,
            ))

    return M3BImpactPlan(
        status=BLOCKED if issues else READY_FOR_REVIEW,
        business_date=day,
        changed_snapshot_fields=tuple(sorted(
            snapshot_impacts, key=lambda x: (x.branch_key, x.kpi_field),
        )),
        track_field_changes=tuple(sorted(
            track_impacts, key=lambda x: (x.branch_key, x.track_field),
        )),
        continuity_days=tuple(sorted(continuity_days)),
        derived_delta_impacts=tuple(sorted(
            derived_impacts, key=lambda x: (x.business_date, x.branch_key, x.track_mtd_field),
        )),
        blocking_issues=tuple(issues),
        documented_decreases=tuple(documented_decreases),
    )
