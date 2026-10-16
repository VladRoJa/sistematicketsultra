"""M3-B phase 1: PURE impact and MTD-continuity planning, no DB access.

This module never reconstructs, stages, promotes, publishes, queries Warehouse,
or writes Track. Input provenance and branch identities must be verified by
the future authorized caller; synthetic tests exercise its deterministic contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
class M3BImpactPlan:
    status: str
    business_date: date
    changed_snapshot_fields: tuple[M3BSnapshotFieldImpact, ...]
    track_field_changes: tuple[M3BTrackFieldImpact, ...]
    continuity_days: tuple[date, ...]
    derived_delta_impacts: tuple[M3BDerivedDailyImpact, ...]
    blocking_issues: tuple[M3BContinuityIssue, ...]


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


def plan_kpi_desempeno_mtd_impact(
    *,
    business_date: date | str,
    diff: KpiDesempenoSemanticDiffResult,
    observed_mtd: Mapping[date, Mapping[str, Mapping[str, int]]],
) -> M3BImpactPlan:
    """Compute exact impact cells and neighbor-day MTD checks, without IO.

    observed_mtd is indexed by M1's *exact normalized branch_key*, not by
    guessed aliases. No mutation of input maps, Track or Warehouse.
    """
    day = _date(business_date)
    issues: list[M3BContinuityIssue] = []
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
                if (
                    type(field.previous) not in (int, float)
                    or type(field.current) not in (int, float)
                    or (field.field != "alcance_meta" and (
                        int(field.previous) != field.previous
                        or int(field.current) != field.current
                    ))
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
            issues.append(M3BContinuityIssue(
                "MTD_DECREASE", branch, metric, prev_day, day,
                prev_value, corrected, corrected-prev_value,
            ))
        if next_is_same_month and next_value is not None and next_value < corrected:
            issues.append(M3BContinuityIssue(
                "MTD_DECREASE", branch, metric, day, next_day,
                corrected, next_value, next_value-corrected,
            ))

        derived_impacts.append(M3BDerivedDailyImpact(day, branch, metric))
        if next_is_same_month:
            derived_impacts.append(M3BDerivedDailyImpact(next_day, branch, metric))

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
    )
