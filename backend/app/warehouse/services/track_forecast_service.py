from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal, Sequence, TypedDict

from sqlalchemy import Date, Integer, Numeric, and_, bindparam, func, or_, text

from app.extensions import db
from app.models.warehouse import (
    TrackDailyMartORM,
    TrackDailyVersionORM,
    VentaTotalSnapshotORM,
)

from app.warehouse.services.track_branch_cohort_service import (
    TRACK_BRANCH_COHORT_LEGACY_21,
    TRACK_BRANCH_COHORT_NEW_GYMS,
    TRACK_BRANCH_COHORT_TOTAL_ULTRA,
    build_track_branch_cohort_lookup,
    get_track_branch_cohort_definitions,
    get_track_branch_cohort_key,
)


EXCLUDED_BRANCHES = {
    "CORPORATIVO",
    "GIMNASIO PRUEBA",
    "LA_VIGA",
}

_TRACK_DAILY_BRANCH_VERSION_PRIORITY = {
    "cierre_canonico": 0,
    "base_nocturna_canonica": 1,
    "preview_operativo": 2,
}

_TRACK_DAILY_BRANCH_SELECTION_REASONS = {
    "cierre_canonico": "current_canonical_close",
    "base_nocturna_canonica": "current_nightly_base",
    "preview_operativo": "current_operational_preview",
}


class TrackDailyBranchVersionSelection(TypedDict):
    track_date: date
    version_id: int
    version_type: str
    selection_reason: str
    ingreso_real_base_mtd: Decimal | None
    ingreso_real_agregadora_mtd: Decimal | None
    ingreso_real_total_mtd: Decimal | None


class _TrackDailyBranchVersionCandidate(TypedDict):
    track_date: date
    version_id: int
    version_type: str
    ingreso_real_base_mtd: Decimal | None
    ingreso_real_agregadora_mtd: Decimal | None
    ingreso_real_total_mtd: Decimal | None


class BranchHistoricalDailyPoint(TypedDict):
    day: int
    date: date
    daily_total: Decimal
    cumulative_total: Decimal
    has_positive_sale_row: bool


class BranchHistoricalYearSeries(TypedDict):
    year: int
    business_month: date
    status: Literal[
        "available",
        "no_canonical_snapshot",
        "no_branch_rows",
    ]
    snapshot_id: int | None
    snapshot_business_date: date | None
    days_in_month: int
    days_with_positive_sale_row: int
    first_positive_sale_date: date | None
    last_positive_sale_date: date | None
    mtd_at_cutoff: Decimal | None
    full_month_total: Decimal | None
    points: list[BranchHistoricalDailyPoint]


BranchCalendarAlignedStatus = Literal[
    "available",
    "available_with_fallback",
    "no_comparable_history",
    "missing_cutoff_progress",
    "non_positive_segment_weight",
    "missing_calendar_sample",
]


class BranchCalendarAlignedHistoricalSample(TypedDict):
    year: int
    source_date: date
    source_day: int
    source_weekday: str
    source_weekday_ordinal: int
    alignment_kind: Literal[
        "exact_ordinal_match",
        "last_weekday_occurrence_fallback",
    ]
    source_daily_total: Decimal
    source_full_month_total: Decimal
    sample_daily_share: Decimal


class BranchCalendarAlignedDailyPoint(TypedDict):
    day: int
    date: date
    weekday: str
    weekday_index: int
    weekday_ordinal: int
    alignment_key: str
    raw_daily_weight: Decimal | None
    normalized_daily_weight: Decimal | None
    cumulative_weight: Decimal | None
    samples_count: int
    sample_years: list[int]
    used_fallback: bool
    historical_samples: list[BranchCalendarAlignedHistoricalSample]


class BranchCalendarAlignedDistribution(TypedDict):
    status: BranchCalendarAlignedStatus
    method: Literal["weekday_ordinal_aligned_historical_weights"]
    target_month: date
    cutoff_day: int
    historical_progress_pct_at_cutoff: Decimal | None
    comparison_years_requested: list[int]
    comparison_years_used: list[int]
    comparison_years_excluded: list[BranchHistoricalExpectedExcludedYear]
    exact_matches_count: int
    fallback_matches_count: int
    points: list[BranchCalendarAlignedDailyPoint]


class BranchHistoricalExpectedDailyPoint(TypedDict):
    day: int
    date: date
    historical_progress_pct: Decimal
    expected_daily_total: Decimal
    expected_cumulative_total: Decimal
    sample_years: list[int]
    samples_count: int


class BranchHistoricalExpectedExcludedYear(TypedDict):
    year: int
    reason: str


class BranchHistoricalExpectedCurve(TypedDict):
    status: Literal[
        "available",
        "no_comparable_history",
        "missing_expected_month_total",
    ]
    method: str
    target_month: date
    cutoff_day: int
    comparison_years_requested: list[int]
    comparison_years_used: list[int]
    comparison_years_excluded: list[BranchHistoricalExpectedExcludedYear]
    samples_count: int
    historical_expected_month_total: Decimal | None
    historical_progress_pct_at_cutoff: Decimal | None
    historical_expected_mtd_at_cutoff: Decimal | None
    distribution_status: BranchCalendarAlignedStatus | None
    calendar_alignment_applied: bool
    points: list[BranchHistoricalExpectedDailyPoint]


BranchProjectedPathMetricBasis = Literal["base_mtd", "total_mtd"]
BranchProjectedDailyPathStatus = Literal[
    "available",
    "expected_curve_unavailable",
    "missing_current_mtd",
    "missing_projected_close",
    "projection_below_current_mtd",
    "no_remaining_historical_progress",
    "inconsistent_month_end_projection",
]


class BranchProjectedDailyPoint(TypedDict):
    day: int
    date: date
    point_kind: Literal["cutoff_anchor", "projected_future"]
    historical_progress_pct: Decimal
    remaining_progress_share: Decimal
    projected_daily_increment: Decimal
    projected_cumulative_total: Decimal


class BranchProjectedDailyPath(TypedDict):
    status: BranchProjectedDailyPathStatus
    method: str
    metric_basis: BranchProjectedPathMetricBasis
    target_month: date
    cutoff_day: int
    current_mtd_at_cutoff: Decimal | None
    projected_close: Decimal | None
    projected_remaining: Decimal | None
    historical_progress_pct_at_cutoff: Decimal | None
    remaining_historical_progress: Decimal | None
    comparison_years_used: list[int]
    samples_count: int
    points: list[BranchProjectedDailyPoint]


BranchGoalPaceStatus = Literal[
    "available",
    "no_goal",
    "partial_goal",
    "invalid_goal",
    "historical_curve_unavailable",
    "projection_unavailable",
]


class BranchGoalPacePoint(TypedDict):
    day: int
    date: date
    historical_progress_pct: Decimal
    goal_expected_daily: Decimal
    goal_expected_cumulative: Decimal


class BranchGoalPaceDetail(TypedDict):
    status: BranchGoalPaceStatus
    metric_basis: Literal["total_mtd"]
    goal_metric_basis: Literal["total_mtd"]
    distribution_basis: Literal["venta_total_base"]
    method: Literal["goal_month_by_weekday_ordinal_aligned_historical_weights"]
    includes_agregadoras: Literal[True]
    aggregadoras_assumed_same_daily_shape: Literal[True]
    comparability_note: str
    goal_month: Decimal | None
    goal_expected_mtd_at_cutoff: Decimal | None
    real_mtd_at_cutoff: Decimal | None
    gap_vs_goal_pace: Decimal | None
    gap_vs_goal_pace_pct: Decimal | None
    remaining_to_goal: Decimal | None
    remaining_days: int
    required_daily_average: Decimal | None
    projected_close: Decimal | None
    projected_gap_to_goal: Decimal | None
    projected_goal_attainment_pct: Decimal | None
    points: list[BranchGoalPacePoint]
    projected_path: BranchProjectedDailyPath | None


class BranchForecastDetailConsistencyError(RuntimeError):
    """Raised when detail sources disagree with the resolved base forecast."""


def _get_track_daily_branch_version_candidates(
    *,
    sucursal_canon: str,
    start_date: date,
    cutoff_date: date,
    resolved_cutoff_version_id: int,
) -> list[_TrackDailyBranchVersionCandidate]:
    rows = (
        db.session.query(TrackDailyVersionORM, TrackDailyMartORM)
        .join(
            TrackDailyMartORM,
            TrackDailyMartORM.track_daily_version_id == TrackDailyVersionORM.id,
        )
        .filter(
            func.upper(func.trim(TrackDailyMartORM.sucursal_canon))
            == sucursal_canon,
            TrackDailyMartORM.track_date == TrackDailyVersionORM.track_date,
            TrackDailyVersionORM.track_date.between(start_date, cutoff_date),
            or_(
                and_(
                    TrackDailyVersionORM.track_date == cutoff_date,
                    TrackDailyVersionORM.id == resolved_cutoff_version_id,
                ),
                and_(
                    TrackDailyVersionORM.track_date < cutoff_date,
                    TrackDailyVersionORM.status == "success",
                    TrackDailyVersionORM.is_current.is_(True),
                    TrackDailyVersionORM.version_type.in_(
                        tuple(_TRACK_DAILY_BRANCH_VERSION_PRIORITY)
                    ),
                ),
            ),
        )
        .order_by(
            TrackDailyVersionORM.track_date.asc(),
            TrackDailyVersionORM.id.desc(),
        )
        .all()
    )

    return [
        {
            "track_date": version.track_date,
            "version_id": version.id,
            "version_type": version.version_type,
            "ingreso_real_base_mtd": mart_row.ingreso_real_base_mtd,
            "ingreso_real_agregadora_mtd": mart_row.ingreso_real_agregadora_mtd,
            "ingreso_real_total_mtd": mart_row.ingreso_real_total_mtd,
        }
        for version, mart_row in rows
    ]


def _select_track_daily_branch_version_candidates(
    *,
    candidates: list[_TrackDailyBranchVersionCandidate],
    cutoff_date: date,
    resolved_cutoff_version_id: int,
) -> list[tuple[_TrackDailyBranchVersionCandidate, str]]:
    selected_by_date: dict[
        date,
        tuple[_TrackDailyBranchVersionCandidate, str],
    ] = {}

    for candidate in candidates:
        candidate_date = candidate["track_date"]
        candidate_version_id = candidate["version_id"]

        if candidate_date == cutoff_date:
            if candidate_version_id == resolved_cutoff_version_id:
                selected_by_date[candidate_date] = (
                    candidate,
                    "resolved_cutoff_version",
                )
            continue

        candidate_version_type = candidate["version_type"]
        selection_reason = _TRACK_DAILY_BRANCH_SELECTION_REASONS[
            candidate_version_type
        ]
        current = selected_by_date.get(candidate_date)

        if current is None:
            selected_by_date[candidate_date] = (candidate, selection_reason)
            continue

        current_candidate = current[0]
        candidate_rank = (
            _TRACK_DAILY_BRANCH_VERSION_PRIORITY[candidate_version_type],
            -candidate_version_id,
        )
        current_rank = (
            _TRACK_DAILY_BRANCH_VERSION_PRIORITY[current_candidate["version_type"]],
            -current_candidate["version_id"],
        )

        if candidate_rank < current_rank:
            selected_by_date[candidate_date] = (candidate, selection_reason)

    cutoff_selection = selected_by_date.get(cutoff_date)
    if cutoff_selection is None:
        raise ValueError(
            "La versión resuelta del corte no tiene una fila TrackDailyMart "
            "para la sucursal solicitada."
        )

    return [selected_by_date[track_date] for track_date in sorted(selected_by_date)]


def _build_track_daily_branch_version_selection(
    candidate: _TrackDailyBranchVersionCandidate,
    *,
    selection_reason: str,
) -> TrackDailyBranchVersionSelection:
    return {
        "track_date": candidate["track_date"],
        "version_id": candidate["version_id"],
        "version_type": candidate["version_type"],
        "selection_reason": selection_reason,
        "ingreso_real_base_mtd": candidate["ingreso_real_base_mtd"],
        "ingreso_real_agregadora_mtd": candidate[
            "ingreso_real_agregadora_mtd"
        ],
        "ingreso_real_total_mtd": candidate["ingreso_real_total_mtd"],
    }


def select_track_daily_branch_versions(
    *,
    sucursal_canon: str,
    start_date: date,
    cutoff_date: date,
    resolved_cutoff_version_id: int,
) -> list[TrackDailyBranchVersionSelection]:
    normalized_branch = str(sucursal_canon or "").strip().upper()
    if not normalized_branch:
        raise ValueError("sucursal_canon es requerido.")

    if start_date > cutoff_date:
        raise ValueError("start_date no puede ser posterior a cutoff_date.")

    candidates = _get_track_daily_branch_version_candidates(
        sucursal_canon=normalized_branch,
        start_date=start_date,
        cutoff_date=cutoff_date,
        resolved_cutoff_version_id=resolved_cutoff_version_id,
    )
    selected_candidates = _select_track_daily_branch_version_candidates(
        candidates=candidates,
        cutoff_date=cutoff_date,
        resolved_cutoff_version_id=resolved_cutoff_version_id,
    )

    return [
        _build_track_daily_branch_version_selection(
            candidate,
            selection_reason=selection_reason,
        )
        for candidate, selection_reason in selected_candidates
    ]


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)

    return date(value.year, value.month + 1, 1)


def _resolve_latest_canonical_snapshots_by_year(
    *,
    business_months: Sequence[date],
) -> dict[int, VentaTotalSnapshotORM]:
    if not business_months:
        return {}

    month_filters = [
        and_(
            VentaTotalSnapshotORM.business_date >= business_month,
            VentaTotalSnapshotORM.business_date < _next_month(business_month),
        )
        for business_month in business_months
    ]
    snapshots = (
        db.session.query(VentaTotalSnapshotORM)
        .filter(
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
            or_(*month_filters),
        )
        .all()
    )

    selected_by_year: dict[int, VentaTotalSnapshotORM] = {}
    for snapshot in snapshots:
        year = snapshot.business_date.year
        current = selected_by_year.get(year)
        if current is None or (
            snapshot.business_date,
            snapshot.captured_at,
            snapshot.id,
        ) > (
            current.business_date,
            current.captured_at,
            current.id,
        ):
            selected_by_year[year] = snapshot

    return selected_by_year


def _load_branch_daily_totals_by_snapshot(
    *,
    snapshot_ids: Sequence[int],
    sucursal_canon: str,
) -> dict[int, dict[date, Decimal]]:
    if not snapshot_ids:
        return {}

    statement = (
        text(
            """
            SELECT
                snapshot_id,
                sale_date,
                total
            FROM track_venta_total_daily_branch_agg
            WHERE snapshot_id IN :snapshot_ids
              AND upper(trim(sucursal_canon)) = :sucursal_canon
            ORDER BY snapshot_id, sale_date
            """
        )
        .bindparams(bindparam("snapshot_ids", expanding=True))
        .columns(
            snapshot_id=Integer,
            sale_date=Date,
            total=Numeric(18, 2),
        )
    )
    rows = db.session.execute(
        statement,
        {
            "snapshot_ids": tuple(snapshot_ids),
            "sucursal_canon": sucursal_canon,
        },
    ).mappings().all()

    totals_by_snapshot: dict[int, dict[date, Decimal]] = {}
    for row in rows:
        snapshot_id = int(row["snapshot_id"])
        sale_date = row["sale_date"]
        total = row["total"]
        decimal_total = (
            total if isinstance(total, Decimal) else Decimal(str(total))
        )
        daily_totals = totals_by_snapshot.setdefault(snapshot_id, {})
        daily_totals[sale_date] = (
            daily_totals.get(sale_date, Decimal("0")) + decimal_total
        )

    return totals_by_snapshot


def _build_available_branch_historical_year_series(
    *,
    year: int,
    business_month: date,
    snapshot: VentaTotalSnapshotORM,
    daily_totals: dict[date, Decimal],
    cutoff_day: int,
) -> BranchHistoricalYearSeries:
    days_in_month = monthrange(year, business_month.month)[1]
    cumulative_total = Decimal("0")
    points: list[BranchHistoricalDailyPoint] = []

    for day in range(1, days_in_month + 1):
        point_date = date(year, business_month.month, day)
        has_positive_sale_row = point_date in daily_totals
        daily_total = daily_totals.get(point_date, Decimal("0"))
        cumulative_total += daily_total
        points.append(
            {
                "day": day,
                "date": point_date,
                "daily_total": daily_total,
                "cumulative_total": cumulative_total,
                "has_positive_sale_row": has_positive_sale_row,
            }
        )

    positive_sale_dates = sorted(daily_totals)
    effective_cutoff_day = min(cutoff_day, days_in_month)
    return {
        "year": year,
        "business_month": business_month,
        "status": "available",
        "snapshot_id": snapshot.id,
        "snapshot_business_date": snapshot.business_date,
        "days_in_month": days_in_month,
        "days_with_positive_sale_row": len(positive_sale_dates),
        "first_positive_sale_date": positive_sale_dates[0],
        "last_positive_sale_date": positive_sale_dates[-1],
        "mtd_at_cutoff": points[effective_cutoff_day - 1]["cumulative_total"],
        "full_month_total": cumulative_total,
        "points": points,
    }


def _build_empty_branch_historical_year_series(
    *,
    year: int,
    business_month: date,
    status: Literal["no_canonical_snapshot", "no_branch_rows"],
    snapshot: VentaTotalSnapshotORM | None,
) -> BranchHistoricalYearSeries:
    return {
        "year": year,
        "business_month": business_month,
        "status": status,
        "snapshot_id": snapshot.id if snapshot is not None else None,
        "snapshot_business_date": (
            snapshot.business_date if snapshot is not None else None
        ),
        "days_in_month": monthrange(year, business_month.month)[1],
        "days_with_positive_sale_row": 0,
        "first_positive_sale_date": None,
        "last_positive_sale_date": None,
        "mtd_at_cutoff": None,
        "full_month_total": None,
        "points": [],
    }


def build_branch_historical_daily_series(
    *,
    sucursal_canon: str,
    target_month: date,
    comparison_years: Sequence[int],
    cutoff_day: int,
) -> list[BranchHistoricalYearSeries]:
    normalized_branch = str(sucursal_canon or "").strip().upper()
    if not normalized_branch:
        raise ValueError("sucursal_canon es requerido.")

    if cutoff_day < 1:
        raise ValueError("cutoff_day debe ser mayor o igual a 1.")

    if any(not isinstance(year, int) or not 1 <= year <= 9999 for year in comparison_years):
        raise ValueError("comparison_years debe contener años válidos.")

    years = sorted(set(comparison_years))
    business_months = [
        date(year, target_month.month, 1)
        for year in years
    ]
    snapshots_by_year = _resolve_latest_canonical_snapshots_by_year(
        business_months=business_months,
    )
    daily_totals_by_snapshot = _load_branch_daily_totals_by_snapshot(
        snapshot_ids=[snapshot.id for snapshot in snapshots_by_year.values()],
        sucursal_canon=normalized_branch,
    )

    series: list[BranchHistoricalYearSeries] = []
    for business_month in business_months:
        year = business_month.year
        snapshot = snapshots_by_year.get(year)
        if snapshot is None:
            series.append(
                _build_empty_branch_historical_year_series(
                    year=year,
                    business_month=business_month,
                    status="no_canonical_snapshot",
                    snapshot=None,
                )
            )
            continue

        daily_totals = daily_totals_by_snapshot.get(snapshot.id)
        if not daily_totals:
            series.append(
                _build_empty_branch_historical_year_series(
                    year=year,
                    business_month=business_month,
                    status="no_branch_rows",
                    snapshot=snapshot,
                )
            )
            continue

        series.append(
            _build_available_branch_historical_year_series(
                year=year,
                business_month=business_month,
                snapshot=snapshot,
                daily_totals=daily_totals,
                cutoff_day=cutoff_day,
            )
        )

    return series


_WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def build_branch_calendar_aligned_daily_weights(
    *,
    historical_series: Sequence[BranchHistoricalYearSeries],
    target_month: date,
    cutoff_day: int,
    historical_progress_pct_at_cutoff: Decimal | None,
) -> BranchCalendarAlignedDistribution:
    target_month = target_month.replace(day=1)
    target_days_in_month = monthrange(target_month.year, target_month.month)[1]
    if not 1 <= cutoff_day <= target_days_in_month:
        raise ValueError("cutoff_day debe pertenecer a target_month.")

    method = "weekday_ordinal_aligned_historical_weights"
    comparison_years_requested = sorted(
        {series["year"] for series in historical_series}
    )
    usable_series: list[tuple[BranchHistoricalYearSeries, Decimal]] = []
    excluded_years: list[BranchHistoricalExpectedExcludedYear] = []
    for series in historical_series:
        if series["status"] != "available":
            excluded_years.append(
                {"year": series["year"], "reason": series["status"]}
            )
            continue
        if not series["points"]:
            excluded_years.append(
                {"year": series["year"], "reason": "no_points"}
            )
            continue
        full_month_total = series["full_month_total"]
        if full_month_total is None or full_month_total <= 0:
            excluded_years.append(
                {
                    "year": series["year"],
                    "reason": "non_positive_full_month_total",
                }
            )
            continue
        usable_series.append((series, full_month_total))

    comparison_years_used = [series["year"] for series, _ in usable_series]
    points: list[BranchCalendarAlignedDailyPoint] = []
    exact_matches_count = 0
    fallback_matches_count = 0

    for target_day in range(1, target_days_in_month + 1):
        target_date = target_month.replace(day=target_day)
        weekday_index = target_date.weekday()
        weekday = _WEEKDAY_KEYS[weekday_index]
        weekday_ordinal = ((target_day - 1) // 7) + 1
        historical_samples: list[BranchCalendarAlignedHistoricalSample] = []

        for series, full_month_total in usable_series:
            weekday_points = [
                point
                for point in series["points"]
                if point["date"].weekday() == weekday_index
            ]
            source_point: BranchHistoricalDailyPoint | None = None
            alignment_kind: Literal[
                "exact_ordinal_match",
                "last_weekday_occurrence_fallback",
            ] = "exact_ordinal_match"
            if len(weekday_points) >= weekday_ordinal:
                source_point = weekday_points[weekday_ordinal - 1]
            elif weekday_ordinal == 5 and weekday_points:
                source_point = weekday_points[-1]
                alignment_kind = "last_weekday_occurrence_fallback"

            if source_point is None:
                continue

            if alignment_kind == "exact_ordinal_match":
                exact_matches_count += 1
            else:
                fallback_matches_count += 1
            source_date = source_point["date"]
            source_daily_total = source_point["daily_total"]
            historical_samples.append(
                {
                    "year": series["year"],
                    "source_date": source_date,
                    "source_day": source_point["day"],
                    "source_weekday": _WEEKDAY_KEYS[source_date.weekday()],
                    "source_weekday_ordinal": ((source_date.day - 1) // 7) + 1,
                    "alignment_kind": alignment_kind,
                    "source_daily_total": source_daily_total,
                    "source_full_month_total": full_month_total,
                    "sample_daily_share": source_daily_total / full_month_total,
                }
            )

        raw_daily_weight = None
        if historical_samples:
            raw_daily_weight = sum(
                (sample["source_daily_total"] for sample in historical_samples),
                Decimal("0"),
            ) / sum(
                (
                    sample["source_full_month_total"]
                    for sample in historical_samples
                ),
                Decimal("0"),
            )
        points.append(
            {
                "day": target_day,
                "date": target_date,
                "weekday": weekday,
                "weekday_index": weekday_index,
                "weekday_ordinal": weekday_ordinal,
                "alignment_key": f"{weekday}:{weekday_ordinal}",
                "raw_daily_weight": raw_daily_weight,
                "normalized_daily_weight": None,
                "cumulative_weight": None,
                "samples_count": len(historical_samples),
                "sample_years": sorted(
                    sample["year"] for sample in historical_samples
                ),
                "used_fallback": any(
                    sample["alignment_kind"]
                    == "last_weekday_occurrence_fallback"
                    for sample in historical_samples
                ),
                "historical_samples": historical_samples,
            }
        )

    def result(status: BranchCalendarAlignedStatus) -> BranchCalendarAlignedDistribution:
        return {
            "status": status,
            "method": method,
            "target_month": target_month,
            "cutoff_day": cutoff_day,
            "historical_progress_pct_at_cutoff": (
                historical_progress_pct_at_cutoff
            ),
            "comparison_years_requested": comparison_years_requested,
            "comparison_years_used": comparison_years_used,
            "comparison_years_excluded": excluded_years,
            "exact_matches_count": exact_matches_count,
            "fallback_matches_count": fallback_matches_count,
            "points": points,
        }

    if not usable_series:
        return result("no_comparable_history")
    if any(point["raw_daily_weight"] is None for point in points):
        return result("missing_calendar_sample")
    if (
        historical_progress_pct_at_cutoff is None
        or not historical_progress_pct_at_cutoff.is_finite()
        or not Decimal("0")
        <= historical_progress_pct_at_cutoff
        <= Decimal("1")
        or (
            cutoff_day == target_days_in_month
            and historical_progress_pct_at_cutoff != Decimal("1")
        )
    ):
        return result("missing_cutoff_progress")

    segment_definitions = (
        (range(0, cutoff_day), historical_progress_pct_at_cutoff),
        (
            range(cutoff_day, target_days_in_month),
            Decimal("1") - historical_progress_pct_at_cutoff,
        ),
    )
    for indexes, segment_target in segment_definitions:
        segment_indexes = list(indexes)
        if not segment_indexes:
            continue
        raw_weights = [
            points[index]["raw_daily_weight"] for index in segment_indexes
        ]
        if any(weight is None or weight < 0 for weight in raw_weights):
            return result("non_positive_segment_weight")
        segment_raw_weight = sum(
            (weight for weight in raw_weights if weight is not None),
            Decimal("0"),
        )
        if segment_raw_weight <= 0:
            return result("non_positive_segment_weight")

        normalized_before_last = Decimal("0")
        for index in segment_indexes[:-1]:
            raw_weight = points[index]["raw_daily_weight"]
            assert raw_weight is not None
            normalized_weight = (
                raw_weight / segment_raw_weight * segment_target
            )
            points[index]["normalized_daily_weight"] = normalized_weight
            normalized_before_last += normalized_weight
        last_normalized_weight = segment_target - normalized_before_last
        if last_normalized_weight < 0:
            return result("non_positive_segment_weight")
        points[segment_indexes[-1]]["normalized_daily_weight"] = (
            last_normalized_weight
        )

    cumulative_weight = Decimal("0")
    for point in points:
        normalized_weight = point["normalized_daily_weight"]
        if normalized_weight is None or normalized_weight < 0:
            return result("non_positive_segment_weight")
        cumulative_weight += normalized_weight
        point["cumulative_weight"] = cumulative_weight
    points[-1]["cumulative_weight"] = Decimal("1")

    return result(
        "available_with_fallback"
        if fallback_matches_count
        else "available"
    )


def build_branch_historical_expected_daily_curve(
    *,
    historical_series: Sequence[BranchHistoricalYearSeries],
    target_month: date,
    cutoff_day: int,
    historical_expected_month_total: Decimal | None,
) -> BranchHistoricalExpectedCurve:
    target_month = target_month.replace(day=1)
    target_days_in_month = monthrange(target_month.year, target_month.month)[1]
    if not 1 <= cutoff_day <= target_days_in_month:
        raise ValueError("cutoff_day debe pertenecer a target_month.")

    comparison_years_requested = sorted(
        {series["year"] for series in historical_series}
    )
    usable_series: list[tuple[BranchHistoricalYearSeries, Decimal]] = []
    excluded_years: list[BranchHistoricalExpectedExcludedYear] = []

    for series in historical_series:
        if series["status"] != "available":
            excluded_years.append(
                {"year": series["year"], "reason": series["status"]}
            )
            continue

        if not series["points"]:
            excluded_years.append(
                {"year": series["year"], "reason": "no_points"}
            )
            continue

        full_month_total = series["full_month_total"]
        if full_month_total is None or full_month_total <= 0:
            excluded_years.append(
                {
                    "year": series["year"],
                    "reason": "non_positive_full_month_total",
                }
            )
            continue

        usable_series.append((series, full_month_total))

    comparison_years_used = [series["year"] for series, _ in usable_series]
    method = "aggregate_cumulative_total_divided_by_aggregate_month_total"

    def empty_result(
        status: Literal[
            "no_comparable_history",
            "missing_expected_month_total",
        ],
    ) -> BranchHistoricalExpectedCurve:
        return {
            "status": status,
            "method": method,
            "target_month": target_month,
            "cutoff_day": cutoff_day,
            "comparison_years_requested": comparison_years_requested,
            "comparison_years_used": comparison_years_used,
            "comparison_years_excluded": excluded_years,
            "samples_count": len(usable_series),
            "historical_expected_month_total": historical_expected_month_total,
            "historical_progress_pct_at_cutoff": None,
            "historical_expected_mtd_at_cutoff": None,
            "points": [],
        }

    if historical_expected_month_total is None:
        return empty_result("missing_expected_month_total")

    if not usable_series:
        return empty_result("no_comparable_history")

    aggregate_month_total = sum(
        (full_month_total for _, full_month_total in usable_series),
        Decimal("0"),
    )
    sample_years = comparison_years_used.copy()
    points: list[BranchHistoricalExpectedDailyPoint] = []
    previous_progress = Decimal("0")
    previous_expected_cumulative = Decimal("0")

    for day in range(1, target_days_in_month + 1):
        aggregate_cumulative_total = Decimal("0")
        for series, _ in usable_series:
            # A non-leap February keeps contributing its day-28 close on day 29.
            source_day_index = min(day, len(series["points"])) - 1
            aggregate_cumulative_total += series["points"][source_day_index][
                "cumulative_total"
            ]

        historical_progress_pct = (
            aggregate_cumulative_total / aggregate_month_total
        )
        if historical_progress_pct < previous_progress:
            historical_progress_pct = previous_progress
        if day == target_days_in_month:
            historical_progress_pct = Decimal("1")

        expected_cumulative_total = (
            historical_expected_month_total * historical_progress_pct
        )
        if day == target_days_in_month:
            expected_cumulative_total = historical_expected_month_total

        expected_daily_total = (
            expected_cumulative_total - previous_expected_cumulative
        )
        if expected_daily_total < 0:
            expected_daily_total = Decimal("0")
            expected_cumulative_total = previous_expected_cumulative

        points.append(
            {
                "day": day,
                "date": target_month.replace(day=day),
                "historical_progress_pct": historical_progress_pct,
                "expected_daily_total": expected_daily_total,
                "expected_cumulative_total": expected_cumulative_total,
                "sample_years": sample_years.copy(),
                "samples_count": len(sample_years),
            }
        )
        previous_progress = historical_progress_pct
        previous_expected_cumulative = expected_cumulative_total

    cutoff_point = points[cutoff_day - 1]
    return {
        "status": "available",
        "method": method,
        "target_month": target_month,
        "cutoff_day": cutoff_day,
        "comparison_years_requested": comparison_years_requested,
        "comparison_years_used": comparison_years_used,
        "comparison_years_excluded": excluded_years,
        "samples_count": len(usable_series),
        "historical_expected_month_total": historical_expected_month_total,
        "historical_progress_pct_at_cutoff": cutoff_point[
            "historical_progress_pct"
        ],
        "historical_expected_mtd_at_cutoff": cutoff_point[
            "expected_cumulative_total"
        ],
        "points": points,
    }


def _build_branch_calendar_aligned_historical_expected_daily_curve(
    *,
    distribution: BranchCalendarAlignedDistribution,
    target_month: date,
    cutoff_day: int,
    historical_expected_month_total: Decimal | None,
) -> BranchHistoricalExpectedCurve:
    target_month = target_month.replace(day=1)
    days_in_month = monthrange(target_month.year, target_month.month)[1]
    if not 1 <= cutoff_day <= days_in_month:
        raise ValueError("cutoff_day debe pertenecer a target_month.")
    if distribution["target_month"] != target_month:
        raise ValueError("distribution no corresponde a target_month.")
    if distribution["cutoff_day"] != cutoff_day:
        raise ValueError("distribution no corresponde a cutoff_day.")

    method = "weekday_ordinal_aligned_historical_weights"

    def empty_result(
        status: Literal[
            "no_comparable_history",
            "missing_expected_month_total",
        ],
    ) -> BranchHistoricalExpectedCurve:
        return {
            "status": status,
            "method": method,
            "target_month": target_month,
            "cutoff_day": cutoff_day,
            "comparison_years_requested": distribution[
                "comparison_years_requested"
            ].copy(),
            "comparison_years_used": distribution[
                "comparison_years_used"
            ].copy(),
            "comparison_years_excluded": [
                dict(item) for item in distribution["comparison_years_excluded"]
            ],
            "samples_count": len(distribution["comparison_years_used"]),
            "historical_expected_month_total": historical_expected_month_total,
            "historical_progress_pct_at_cutoff": distribution[
                "historical_progress_pct_at_cutoff"
            ],
            "historical_expected_mtd_at_cutoff": None,
            "distribution_status": distribution["status"],
            "calendar_alignment_applied": True,
            "points": [],
        }

    if historical_expected_month_total is None:
        return empty_result("missing_expected_month_total")
    if distribution["status"] not in ("available", "available_with_fallback"):
        return empty_result("no_comparable_history")

    points: list[BranchHistoricalExpectedDailyPoint] = []
    previous_expected_cumulative = Decimal("0")
    for distribution_point in distribution["points"]:
        normalized_daily_weight = distribution_point[
            "normalized_daily_weight"
        ]
        cumulative_weight = distribution_point["cumulative_weight"]
        if normalized_daily_weight is None or cumulative_weight is None:
            raise BranchForecastDetailConsistencyError(
                "La distribución calendario disponible contiene pesos nulos."
            )
        expected_cumulative_total = (
            historical_expected_month_total * cumulative_weight
        )
        if distribution_point["day"] == days_in_month:
            expected_cumulative_total = historical_expected_month_total
        expected_daily_total = (
            expected_cumulative_total - previous_expected_cumulative
        )
        if expected_daily_total < 0:
            raise BranchForecastDetailConsistencyError(
                "La distribución calendario produce incrementos históricos negativos."
            )
        points.append(
            {
                "day": distribution_point["day"],
                "date": distribution_point["date"],
                "historical_progress_pct": cumulative_weight,
                "expected_daily_total": expected_daily_total,
                "expected_cumulative_total": expected_cumulative_total,
                "sample_years": distribution_point["sample_years"].copy(),
                "samples_count": distribution_point["samples_count"],
            }
        )
        previous_expected_cumulative = expected_cumulative_total

    cutoff_point = points[cutoff_day - 1]
    return {
        "status": "available",
        "method": method,
        "target_month": target_month,
        "cutoff_day": cutoff_day,
        "comparison_years_requested": distribution[
            "comparison_years_requested"
        ].copy(),
        "comparison_years_used": distribution["comparison_years_used"].copy(),
        "comparison_years_excluded": [
            dict(item) for item in distribution["comparison_years_excluded"]
        ],
        "samples_count": len(distribution["comparison_years_used"]),
        "historical_expected_month_total": historical_expected_month_total,
        "historical_progress_pct_at_cutoff": cutoff_point[
            "historical_progress_pct"
        ],
        "historical_expected_mtd_at_cutoff": cutoff_point[
            "expected_cumulative_total"
        ],
        "distribution_status": distribution["status"],
        "calendar_alignment_applied": True,
        "points": points,
    }


def build_branch_projected_daily_path(
    *,
    expected_curve: BranchHistoricalExpectedCurve,
    target_month: date,
    cutoff_day: int,
    metric_basis: BranchProjectedPathMetricBasis,
    current_mtd_at_cutoff: Decimal | None,
    projected_close: Decimal | None,
) -> BranchProjectedDailyPath:
    target_month = target_month.replace(day=1)
    days_in_month = monthrange(target_month.year, target_month.month)[1]
    if not 1 <= cutoff_day <= days_in_month:
        raise ValueError("cutoff_day debe pertenecer a target_month.")
    if metric_basis not in ("base_mtd", "total_mtd"):
        raise ValueError("metric_basis debe ser base_mtd o total_mtd.")

    method = "historical_remaining_daily_weights"
    comparison_years_used = expected_curve["comparison_years_used"].copy()
    samples_count = expected_curve["samples_count"]
    projected_remaining = (
        projected_close - current_mtd_at_cutoff
        if projected_close is not None and current_mtd_at_cutoff is not None
        else None
    )

    def empty_result(
        status: BranchProjectedDailyPathStatus,
        *,
        historical_progress_pct_at_cutoff: Decimal | None = None,
        remaining_historical_progress: Decimal | None = None,
    ) -> BranchProjectedDailyPath:
        return {
            "status": status,
            "method": method,
            "metric_basis": metric_basis,
            "target_month": target_month,
            "cutoff_day": cutoff_day,
            "current_mtd_at_cutoff": current_mtd_at_cutoff,
            "projected_close": projected_close,
            "projected_remaining": projected_remaining,
            "historical_progress_pct_at_cutoff": (
                historical_progress_pct_at_cutoff
            ),
            "remaining_historical_progress": remaining_historical_progress,
            "comparison_years_used": comparison_years_used,
            "samples_count": samples_count,
            "points": [],
        }

    if expected_curve["status"] != "available":
        return empty_result("expected_curve_unavailable")
    if current_mtd_at_cutoff is None:
        return empty_result("missing_current_mtd")
    if projected_close is None:
        return empty_result("missing_projected_close")
    if projected_close < current_mtd_at_cutoff:
        return empty_result("projection_below_current_mtd")

    expected_points_by_day = {
        point["day"]: point for point in expected_curve["points"]
    }
    cutoff_expected_point = expected_points_by_day.get(cutoff_day)
    if cutoff_expected_point is None:
        raise ValueError("expected_curve no contiene el día de corte.")

    historical_progress_at_cutoff = cutoff_expected_point[
        "historical_progress_pct"
    ]
    remaining_historical_progress = (
        Decimal("1") - historical_progress_at_cutoff
    )

    if cutoff_day == days_in_month:
        if projected_close != current_mtd_at_cutoff:
            return empty_result(
                "inconsistent_month_end_projection",
                historical_progress_pct_at_cutoff=historical_progress_at_cutoff,
                remaining_historical_progress=remaining_historical_progress,
            )

        anchor: BranchProjectedDailyPoint = {
            "day": cutoff_day,
            "date": target_month.replace(day=cutoff_day),
            "point_kind": "cutoff_anchor",
            "historical_progress_pct": historical_progress_at_cutoff,
            "remaining_progress_share": Decimal("0"),
            "projected_daily_increment": Decimal("0"),
            "projected_cumulative_total": current_mtd_at_cutoff,
        }
        result = empty_result(
            "available",
            historical_progress_pct_at_cutoff=historical_progress_at_cutoff,
            remaining_historical_progress=remaining_historical_progress,
        )
        result["points"] = [anchor]
        return result

    if remaining_historical_progress <= 0:
        return empty_result(
            "no_remaining_historical_progress",
            historical_progress_pct_at_cutoff=historical_progress_at_cutoff,
            remaining_historical_progress=remaining_historical_progress,
        )

    points: list[BranchProjectedDailyPoint] = [
        {
            "day": cutoff_day,
            "date": target_month.replace(day=cutoff_day),
            "point_kind": "cutoff_anchor",
            "historical_progress_pct": historical_progress_at_cutoff,
            "remaining_progress_share": Decimal("0"),
            "projected_daily_increment": Decimal("0"),
            "projected_cumulative_total": current_mtd_at_cutoff,
        }
    ]
    previous_cumulative = current_mtd_at_cutoff

    for day in range(cutoff_day + 1, days_in_month + 1):
        expected_point = expected_points_by_day.get(day)
        if expected_point is None:
            raise ValueError(f"expected_curve no contiene el día {day}.")

        historical_progress_pct = expected_point["historical_progress_pct"]
        remaining_progress_share = (
            historical_progress_pct - historical_progress_at_cutoff
        ) / remaining_historical_progress
        projected_cumulative_total = (
            current_mtd_at_cutoff
            + projected_remaining * remaining_progress_share
        )
        if day == days_in_month:
            remaining_progress_share = Decimal("1")
            projected_cumulative_total = projected_close

        projected_daily_increment = (
            projected_cumulative_total - previous_cumulative
        )
        points.append(
            {
                "day": day,
                "date": target_month.replace(day=day),
                "point_kind": "projected_future",
                "historical_progress_pct": historical_progress_pct,
                "remaining_progress_share": remaining_progress_share,
                "projected_daily_increment": projected_daily_increment,
                "projected_cumulative_total": projected_cumulative_total,
            }
        )
        previous_cumulative = projected_cumulative_total

    return {
        "status": "available",
        "method": method,
        "metric_basis": metric_basis,
        "target_month": target_month,
        "cutoff_day": cutoff_day,
        "current_mtd_at_cutoff": current_mtd_at_cutoff,
        "projected_close": projected_close,
        "projected_remaining": projected_remaining,
        "historical_progress_pct_at_cutoff": historical_progress_at_cutoff,
        "remaining_historical_progress": remaining_historical_progress,
        "comparison_years_used": comparison_years_used,
        "samples_count": samples_count,
        "points": points,
    }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


def _first_day_of_month(value: date) -> date:
    return date(value.year, value.month, 1)


def _build_history_window(target_month: date) -> tuple[date, date]:
    return date(target_month.year - 3, 1, 1), date(target_month.year, 1, 1)


def _confidence_from_coverage_months(months_count: int) -> str:
    if months_count >= 24:
        return "alta"

    if months_count >= 12:
        return "media"

    if months_count >= 1:
        return "baja"

    return "sin_historia"


def _confidence_from_comparable_months(months_count: int) -> str:
    if months_count >= 3:
        return "alta"

    if months_count == 2:
        return "media"

    if months_count == 1:
        return "baja"

    return "sin_historia"


def _goal_status_from_count(*, expected_count: int, available_count: int) -> str:
    if expected_count <= 0:
        return "pending"

    if available_count == expected_count:
        return "available"

    if available_count > 0:
        return "partial"

    return "pending"


def _status_vs_goal(*, gap_pct: float | None, progress_pct: float) -> str | None:
    if gap_pct is None:
        return None

    if progress_pct < 0.15:
        return "inicio_mes_baja_confianza"

    if gap_pct <= -0.08:
        return "rojo"

    if gap_pct <= -0.03:
        return "amarillo"

    if gap_pct >= 0.05:
        return "destacado"

    return "en_ritmo"


def _get_selected_mart_rows(
    *,
    track_daily_version_id: int,
    scope: str,
    branch: str | None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "track_daily_version_id": track_daily_version_id,
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
    }

    branch_filter = ""

    if scope == "branch":
        if not branch:
            raise ValueError("branch es requerido cuando scope=branch.")

        params["branch"] = branch.strip().upper()
        branch_filter = "AND upper(trim(sucursal_canon)) = :branch"

    rows = db.session.execute(
        text(
            f"""
            SELECT
                sucursal_canon,
                target_month,
                COALESCE(ingreso_real_total_mtd, ingreso_real_mtd, 0) AS real_mtd,
                ingreso_real_base_mtd,
                ingreso_real_agregadora_mtd,
                meta_faycgo_mes
            FROM track_daily_mart
            WHERE track_daily_version_id = :track_daily_version_id
              AND upper(trim(sucursal_canon)) NOT IN :excluded_branches
              {branch_filter}
            ORDER BY sucursal_canon
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]


def _resolve_goal_from_track_monthly_targets(
    *,
    target_month: date,
    selected_branches: list[str],
) -> tuple[float | None, int]:
    if not selected_branches:
        return None, 0

    rows = db.session.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE meta_faycgo_mes IS NOT NULL) AS available_count,
                SUM(meta_faycgo_mes) AS goal_month
            FROM track_monthly_targets
            WHERE target_month = :target_month
              AND is_active = true
              AND sucursal_canon IN :selected_branches
            """
        ).bindparams(bindparam("selected_branches", expanding=True)),
        {
            "target_month": target_month,
            "selected_branches": tuple(selected_branches),
        },
    ).mappings().first()

    if not rows:
        return None, 0

    return _to_float(rows["goal_month"]), int(rows["available_count"] or 0)


def _build_historical_curve(
    *,
    target_month: date,
    cutoff_day: int,
    scope: str,
    branch: str | None,
) -> dict[str, Any]:
    history_start_date, history_end_date = _build_history_window(target_month)

    params: dict[str, Any] = {
        "history_start_date": history_start_date,
        "history_end_date": history_end_date,
        "target_month_number": target_month.month,
        "cutoff_day": cutoff_day,
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
    }

    branch_filter = ""

    if scope == "branch" and branch:
        branch_filter = "AND upper(trim(a.sucursal_canon)) = :branch"
        params["branch"] = branch.strip().upper()

    row = db.session.execute(
        text(
            f"""
            WITH historical AS (
                SELECT
                    a.business_month,
                    a.sale_date,
                    a.day_of_month,
                    upper(trim(a.sucursal_canon)) AS sucursal_canon,
                    a.total
                FROM track_venta_total_daily_branch_agg a
                JOIN venta_total_snapshots s
                  ON s.id = a.snapshot_id
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND a.business_month >= :history_start_date
                  AND a.business_month < :history_end_date
                  AND EXTRACT(MONTH FROM a.business_month)::int = :target_month_number
                  AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
                  {branch_filter}
            )
            SELECT
                COUNT(DISTINCT business_month) AS historical_months,
                COALESCE(SUM(total), 0)::numeric AS historical_month_total,
                COALESCE(SUM(CASE WHEN day_of_month <= :cutoff_day THEN total ELSE 0 END), 0)::numeric AS historical_mtd_total,
                COALESCE(SUM(CASE WHEN day_of_month > :cutoff_day THEN total ELSE 0 END), 0)::numeric AS historical_remaining_total,
                COUNT(DISTINCT day_of_month)::int AS distinct_days
            FROM historical
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        params,
    ).mappings().first()

    historical_months = int(row["historical_months"] or 0) if row else 0
    historical_month_total = float(row["historical_month_total"] or 0) if row else 0.0
    historical_mtd_total = float(row["historical_mtd_total"] or 0) if row else 0.0
    historical_remaining_total = float(row["historical_remaining_total"] or 0) if row else 0.0
    distinct_days = int(row["distinct_days"] or 0) if row else 0

    historical_progress_pct = None

    if historical_month_total > 0:
        historical_progress_pct = historical_mtd_total / historical_month_total

    return {
        "source": "branch" if scope == "branch" else "national",
        "historical_months": historical_months,
        "historical_month_total": historical_month_total,
        "historical_mtd_total": historical_mtd_total,
        "historical_remaining_total": historical_remaining_total,
        "historical_progress_pct": historical_progress_pct,
        "distinct_days": distinct_days,
        "confidence": _confidence_from_comparable_months(historical_months),
    }



def _build_history_coverage(*, target_month: date, branch: str | None) -> dict[str, Any]:
    history_start_date, history_end_date = _build_history_window(target_month)

    if not branch:
        rows = db.session.execute(
            text(
                """
                SELECT
                    COUNT(DISTINCT date_trunc('month', business_date)::date) AS months_count,
                    MIN(date_trunc('month', business_date)::date) AS first_month,
                    MAX(date_trunc('month', business_date)::date) AS last_month
                FROM venta_total_snapshots
                WHERE report_type_key = 'venta_total'
                  AND snapshot_kind = 'daily'
                  AND is_canonical = true
                  AND business_date >= :history_start_date
                  AND business_date < :history_end_date
                """
            ),
            {
                "history_start_date": history_start_date,
                "history_end_date": history_end_date,
            },
        ).mappings().first()

        months_count = int(rows["months_count"] or 0) if rows else 0

        return {
            "months_count": months_count,
            "first_month": rows["first_month"].isoformat() if rows and rows["first_month"] else None,
            "last_month": rows["last_month"].isoformat() if rows and rows["last_month"] else None,
            "confidence": _confidence_from_coverage_months(months_count),
        }

    params: dict[str, Any] = {
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
        "history_start_date": history_start_date,
        "history_end_date": history_end_date,
        "branch": branch.strip().upper(),
    }

    rows = db.session.execute(
        text(
            """
            WITH canonical AS (
                SELECT
                    s.id AS snapshot_id,
                    date_trunc('month', s.business_date)::date AS snapshot_month
                FROM venta_total_snapshots s
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND s.business_date >= :history_start_date
                  AND s.business_date < :history_end_date
            ),
            clean AS (
                SELECT DISTINCT
                    c.snapshot_month,
                    a.sucursal_canon
                FROM canonical c
                JOIN venta_total_snapshot_rows r
                  ON r.snapshot_id = c.snapshot_id
                JOIN track_branch_aliases a
                  ON a.source_family = 'gasca_family'
                 AND a.is_active = true
                 AND upper(trim(a.raw_branch_name)) = upper(trim(r.sucursal))
                WHERE upper(trim(r.estatus)) = 'ACTIVO'
                  AND r.total > 0
                  AND to_date(r.fecha, 'DD-MM-YY') >= c.snapshot_month
                  AND to_date(r.fecha, 'DD-MM-YY') < (c.snapshot_month + interval '1 month')
                  AND upper(trim(r.sucursal)) NOT IN :excluded_branches
                  AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
                  AND upper(trim(a.sucursal_canon)) = :branch
            )
            SELECT
                COUNT(DISTINCT snapshot_month) AS months_count,
                MIN(snapshot_month) AS first_month,
                MAX(snapshot_month) AS last_month
            FROM clean
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        params,
    ).mappings().first()

    months_count = int(rows["months_count"] or 0) if rows else 0

    return {
        "months_count": months_count,
        "first_month": rows["first_month"].isoformat() if rows and rows["first_month"] else None,
        "last_month": rows["last_month"].isoformat() if rows and rows["last_month"] else None,
        "confidence": _confidence_from_coverage_months(months_count),
    }




def _format_currency_mxn(value: float | None) -> str:
    if value is None:
        return "sin dato"

    return f"${value:,.0f} MXN"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "sin dato"

    return f"{value * 100:.1f}%"


def _goal_status_message(goal_status: str) -> str | None:
    if goal_status == "pending":
        return "Meta mensual no cargada. El ritmo contra meta se activará automáticamente cuando exista meta_faycgo_mes."

    if goal_status == "partial":
        return "Meta mensual parcialmente cargada. El ritmo contra meta se mantiene desactivado hasta tener metas completas."

    return None


def _resolve_aggregated_canonical_cutoff(
    *,
    target_month: date,
    track_date: date,
    scope: str,
    branch: str | None,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {
        "target_month": target_month,
        "track_date": track_date,
    }

    branch_filter = ""

    if scope == "branch" and branch:
        branch_filter = "AND upper(trim(a.sucursal_canon)) = :branch"
        params["branch"] = branch.strip().upper()

    row = db.session.execute(
        text(
            f"""
            SELECT
                s.id AS snapshot_id,
                s.business_date,
                COUNT(*)::int AS aggregate_rows,
                MIN(a.sale_date)::date AS first_sale_date,
                MAX(a.sale_date)::date AS last_sale_date,
                COUNT(DISTINCT a.sucursal_canon)::int AS branches
            FROM track_venta_total_daily_branch_agg a
            JOIN venta_total_snapshots s
              ON s.id = a.snapshot_id
            WHERE s.report_type_key = 'venta_total'
              AND s.snapshot_kind = 'daily'
              AND s.is_canonical = true
              AND a.business_month = :target_month
              AND s.business_date <= :track_date
              {branch_filter}
            GROUP BY
                s.id,
                s.business_date
            ORDER BY
                s.business_date DESC,
                s.id DESC
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()

    if not row:
        return None

    return {
        "snapshot_id": int(row["snapshot_id"]),
        "business_date": row["business_date"].isoformat() if row["business_date"] else None,
        "aggregate_rows": int(row["aggregate_rows"] or 0),
        "first_sale_date": row["first_sale_date"].isoformat() if row["first_sale_date"] else None,
        "last_sale_date": row["last_sale_date"].isoformat() if row["last_sale_date"] else None,
        "branches": int(row["branches"] or 0),
    }


def _build_forecast_cutoff(
    *,
    track_date: date,
    target_month: date,
    cutoff_day: int,
    generation_mode: str,
    canonical_cutoff: dict[str, Any] | None,
) -> dict[str, Any]:
    is_official = generation_mode == "official_closed_day"

    return {
        "track_date": track_date.isoformat(),
        "target_month": target_month.isoformat(),
        "cutoff_day": cutoff_day,
        "generation_mode": generation_mode,
        "is_official_forecast": is_official,
        "basis": "official_closed_day" if is_official else "preview_operativo",
        "canonical_cutoff": canonical_cutoff,
        "message": (
            "Proyección basada en día cerrado oficial."
            if is_official
            else "Proyección basada en preview operativo; debe leerse como pulso preliminar, no como cierre oficial."
        ),
    }


def _build_executive_status(
    *,
    projected_close: float | None,
    trend_factor: float | None,
    goal_status: str,
    gap_vs_weighted_goal_pct: float | None,
    branch_projection_quality_issue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if branch_projection_quality_issue:
        return {
            "level": "warning",
            "code": "insufficient_branch_history",
            "title": "Histórico insuficiente para proyectar sucursal",
            "message": branch_projection_quality_issue["message"],
            "primary_metric_label": "Proyección de cierre",
            "primary_metric_value": None,
            "primary_metric_unit": "MXN",
        }

    if projected_close is None:
        return {
            "level": "neutral",
            "code": "no_projection",
            "title": "Sin proyección disponible",
            "message": "No hay histórico suficiente para calcular una proyección confiable.",
            "primary_metric_label": "Proyección de cierre",
            "primary_metric_value": None,
            "primary_metric_unit": "MXN",
        }

    if goal_status == "available" and gap_vs_weighted_goal_pct is not None:
        if gap_vs_weighted_goal_pct <= -0.05:
            level = "danger"
            code = "below_weighted_goal"
            title = "Por debajo de la meta ponderada"
        elif gap_vs_weighted_goal_pct < -0.02:
            level = "warning"
            code = "slightly_below_weighted_goal"
            title = "Ligeramente por debajo de la meta ponderada"
        elif gap_vs_weighted_goal_pct > 0.02:
            level = "success"
            code = "above_weighted_goal"
            title = "Por encima de la meta ponderada"
        else:
            level = "neutral"
            code = "near_weighted_goal"
            title = "Cerca de la meta ponderada"

        return {
            "level": level,
            "code": code,
            "title": title,
            "message": f"La proyección actual de cierre es {_format_currency_mxn(projected_close)}.",
            "primary_metric_label": "Proyección de cierre",
            "primary_metric_value": projected_close,
            "primary_metric_unit": "MXN",
        }

    if trend_factor is None:
        return {
            "level": "neutral",
            "code": "projection_without_trend_factor",
            "title": "Proyección calculada sin factor de tendencia",
            "message": f"La proyección actual de cierre es {_format_currency_mxn(projected_close)}.",
            "primary_metric_label": "Proyección de cierre",
            "primary_metric_value": projected_close,
            "primary_metric_unit": "MXN",
        }

    if trend_factor < 0.85:
        level = "danger"
        code = "well_below_historical_pace"
        title = "Ritmo muy por debajo del histórico"
    elif trend_factor < 0.95:
        level = "warning"
        code = "below_historical_pace"
        title = "Ritmo por debajo del histórico"
    elif trend_factor <= 1.05:
        level = "neutral"
        code = "near_historical_pace"
        title = "Ritmo cercano al histórico"
    else:
        level = "success"
        code = "above_historical_pace"
        title = "Ritmo por encima del histórico"

    return {
        "level": level,
        "code": code,
        "title": title,
        "message": (
            f"El real MTD equivale al {_format_percent(trend_factor)} del promedio histórico esperado al corte. "
            f"La proyección actual de cierre es {_format_currency_mxn(projected_close)}."
        ),
        "primary_metric_label": "Proyección de cierre",
        "primary_metric_value": projected_close,
        "primary_metric_unit": "MXN",
    }


def _build_forecast_explanation(
    *,
    cutoff_day: int,
    real_mtd: float,
    projected_close: float | None,
    progress_pct: float | None,
    historical_mtd_total: float | None,
    trend_factor: float | None,
) -> dict[str, Any]:
    if projected_close is None or progress_pct is None:
        plain_text = "No hay histórico suficiente para explicar la proyección."
    else:
        plain_text = (
            f"Históricamente, al día {cutoff_day} se lleva {_format_percent(progress_pct)} del mes. "
            f"Con un real MTD de {_format_currency_mxn(real_mtd)}, "
            f"el cierre proyectado es {_format_currency_mxn(projected_close)}."
        )

    return {
        "formula_key": "real_mtd_divided_by_historical_progress_pct",
        "formula": "projected_close = real_mtd / historical_progress_pct",
        "plain_text": plain_text,
        "components": {
            "cutoff_day": cutoff_day,
            "real_mtd": real_mtd,
            "historical_progress_pct": progress_pct,
            "historical_expected_mtd": historical_mtd_total,
            "trend_factor": trend_factor,
            "projected_close": projected_close,
        },
    }




def _build_same_day_history(
    *,
    target_month: date,
    cutoff_day: int,
    scope: str,
    branch: str | None,
    real_mtd: float,
    projected_close: float | None,
    progress_pct: float | None,
    trend_factor: float | None,
) -> dict[str, Any]:
    history_start_date, history_end_date = _build_history_window(target_month)

    params: dict[str, Any] = {
        "history_start_date": history_start_date,
        "history_end_date": history_end_date,
        "target_month_number": target_month.month,
        "cutoff_day": cutoff_day,
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
    }

    branch_filter = ""

    if scope == "branch" and branch:
        branch_filter = "AND upper(trim(a.sucursal_canon)) = :branch"
        params["branch"] = branch.strip().upper()

    rows = db.session.execute(
        text(
            f"""
            WITH yearly AS (
                SELECT
                    EXTRACT(YEAR FROM a.business_month)::int AS year,
                    a.business_month,
                    COALESCE(SUM(a.total), 0)::numeric AS month_total,
                    COALESCE(SUM(CASE WHEN a.day_of_month <= :cutoff_day THEN a.total ELSE 0 END), 0)::numeric AS mtd_total,
                    COALESCE(SUM(CASE WHEN a.day_of_month > :cutoff_day THEN a.total ELSE 0 END), 0)::numeric AS remaining_total,
                    COUNT(DISTINCT CASE WHEN a.day_of_month <= :cutoff_day THEN a.day_of_month END)::int AS mtd_days,
                    COUNT(DISTINCT a.day_of_month)::int AS month_days
                FROM track_venta_total_daily_branch_agg a
                JOIN venta_total_snapshots s
                  ON s.id = a.snapshot_id
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND a.business_month >= :history_start_date
                  AND a.business_month < :history_end_date
                  AND EXTRACT(MONTH FROM a.business_month)::int = :target_month_number
                  AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
                  {branch_filter}
                GROUP BY
                    EXTRACT(YEAR FROM a.business_month)::int,
                    a.business_month
            )
            SELECT
                year,
                business_month,
                month_total,
                mtd_total,
                remaining_total,
                mtd_days,
                month_days
            FROM yearly
            ORDER BY year
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        params,
    ).mappings().all()

    items: list[dict[str, Any]] = []

    for row in rows:
        mtd_total = float(row["mtd_total"] or 0)
        month_total = float(row["month_total"] or 0)
        remaining_total = float(row["remaining_total"] or 0)

        progress = None
        gap_current_vs_mtd = None
        gap_current_vs_mtd_pct = None

        if month_total > 0:
            progress = mtd_total / month_total

        if mtd_total > 0:
            gap_current_vs_mtd = real_mtd - mtd_total
            gap_current_vs_mtd_pct = gap_current_vs_mtd / mtd_total

        items.append({
            "year": int(row["year"]),
            "business_month": row["business_month"].isoformat() if row["business_month"] else None,
            "mtd_total": mtd_total,
            "month_total": month_total,
            "remaining_total": remaining_total,
            "progress_pct": progress,
            "mtd_days": int(row["mtd_days"] or 0),
            "month_days": int(row["month_days"] or 0),
            "gap_current_vs_mtd": gap_current_vs_mtd,
            "gap_current_vs_mtd_pct": gap_current_vs_mtd_pct,
        })

    historical_mtd_values = [float(item["mtd_total"] or 0) for item in items if float(item["mtd_total"] or 0) > 0]
    historical_month_values = [float(item["month_total"] or 0) for item in items if float(item["month_total"] or 0) > 0]

    average_mtd = sum(historical_mtd_values) / len(historical_mtd_values) if historical_mtd_values else None
    average_month = sum(historical_month_values) / len(historical_month_values) if historical_month_values else None
    gap_current_vs_average_mtd = real_mtd - average_mtd if average_mtd else None
    gap_current_vs_average_mtd_pct = gap_current_vs_average_mtd / average_mtd if average_mtd else None

    return {
        "source": "branch" if scope == "branch" else "national",
        "branch": branch.strip().upper() if branch else None,
        "target_month": target_month.isoformat(),
        "cutoff_day": cutoff_day,
        "historical_years": len(items),
        "confidence": _confidence_from_comparable_months(len(items)),
        "average": {
            "mtd_total": average_mtd,
            "month_total": average_month,
            "gap_current_vs_average_mtd": gap_current_vs_average_mtd,
            "gap_current_vs_average_mtd_pct": gap_current_vs_average_mtd_pct,
        },
        "current": {
            "year": target_month.year,
            "mtd_total": real_mtd,
            "projected_close": projected_close,
            "historical_progress_pct": progress_pct,
            "trend_factor": trend_factor,
        },
        "items": items,
    }

def _resolve_branch_projection_quality_issue(
    *,
    scope: str,
    curve: dict[str, Any],
    trend_factor: float | None,
) -> dict[str, Any] | None:
    if scope != "branch":
        return None

    historical_months = int(curve.get("historical_months") or 0)
    historical_mtd_total = float(curve.get("historical_mtd_total") or 0)
    historical_expected_mtd = (
        historical_mtd_total / historical_months
        if historical_months > 0
        else 0.0
    )
    confidence = str(curve.get("confidence") or "sin_historia")

    reasons: list[str] = []

    if historical_months < 3:
        reasons.append("La sucursal tiene menos de 3 meses comparables para este mes.")

    if confidence != "alta":
        reasons.append(f"La confianza histórica de la sucursal es {confidence}.")

    if historical_expected_mtd < 50000:
        reasons.append("El promedio histórico esperado MTD de la sucursal es demasiado bajo para proyectar con estabilidad.")

    if trend_factor is not None and trend_factor > 3:
        reasons.append("El factor de tendencia es extremo contra el histórico esperado de la sucursal.")

    if not reasons:
        return None

    return {
        "code": "insufficient_branch_history",
        "severity": "warning",
        "message": "Histórico insuficiente para proyectar esta sucursal con estabilidad.",
        "reasons": reasons,
        "thresholds": {
            "min_historical_months": 3,
            "min_historical_mtd_total": 50000,
            "max_trend_factor": 3,
        },
    }

def _build_forecast_warnings(
    *,
    generation_mode: str,
    goal_status: str,
    curve: dict[str, Any],
    canonical_cutoff: dict[str, Any] | None,
    branch_projection_quality_issue: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    if generation_mode != "official_closed_day":
        warnings.append({
            "code": "preview_operativo",
            "severity": "warning",
            "message": "La proyección usa preview operativo; si el día aún no está cerrado, puede variar o subestimar el cierre.",
        })

    if goal_status == "pending":
        warnings.append({
            "code": "goal_pending",
            "severity": "info",
            "message": "La meta mensual no está cargada. La brecha contra meta se activará cuando exista meta_faycgo_mes.",
        })
    elif goal_status == "partial":
        warnings.append({
            "code": "goal_partial",
            "severity": "warning",
            "message": "La meta mensual está parcialmente cargada. El ritmo contra meta se mantiene desactivado.",
        })

    if not canonical_cutoff:
        warnings.append({
            "code": "canonical_cutoff_missing",
            "severity": "warning",
            "message": "No se encontró corte canónico agregado para el mes y fecha solicitados.",
        })

    if int(curve.get("historical_months") or 0) < 3:
        warnings.append({
            "code": "low_comparable_history",
            "severity": "warning",
            "message": "La curva histórica tiene menos de 3 meses comparables.",
        })

    if branch_projection_quality_issue:
        warnings.append(branch_projection_quality_issue)

    return warnings


def _build_branch_drivers(
    *,
    target_month: date,
    cutoff_day: int,
    scope: str,
    mart_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if scope != "national":
        return {
            "status": "not_applicable",
            "scope": scope,
            "metric": "real_mtd_vs_historical_expected_mtd",
            "items": [],
        }

    if not mart_rows:
        return {
            "status": "empty",
            "scope": scope,
            "metric": "real_mtd_vs_historical_expected_mtd",
            "items": [],
        }

    history_start_date, history_end_date = _build_history_window(target_month)

    real_by_branch: dict[str, dict[str, Any]] = {}

    for row in mart_rows:
        sucursal_canon = str(row.get("sucursal_canon") or "").strip().upper()

        if not sucursal_canon:
            continue

        real_by_branch[sucursal_canon] = {
            "sucursal_canon": sucursal_canon,
            "real_mtd": _to_float(row.get("real_mtd")) or 0.0,
            "real_base_mtd": _to_float(row.get("ingreso_real_base_mtd")) or 0.0,
            "real_agregadora_mtd": _to_float(row.get("ingreso_real_agregadora_mtd")) or 0.0,
        }

    selected_branches = tuple(real_by_branch.keys())

    if not selected_branches:
        return {
            "status": "empty",
            "scope": scope,
            "metric": "real_mtd_vs_historical_expected_mtd",
            "items": [],
        }

    rows = db.session.execute(
        text(
            """
            WITH historical AS (
                SELECT
                    upper(trim(a.sucursal_canon)) AS sucursal_canon,
                    a.business_month,
                    a.day_of_month,
                    a.total
                FROM track_venta_total_daily_branch_agg a
                JOIN venta_total_snapshots s
                  ON s.id = a.snapshot_id
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND a.business_month >= :history_start_date
                  AND a.business_month < :history_end_date
                  AND EXTRACT(MONTH FROM a.business_month)::int = :target_month_number
                  AND upper(trim(a.sucursal_canon)) IN :selected_branches
                  AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
            )
            SELECT
                h.sucursal_canon,
                COALESCE(c.track_label, h.sucursal_canon) AS track_label,
                c.display_order,
                COUNT(DISTINCT h.business_month)::int AS historical_months,
                COALESCE(SUM(h.total), 0)::numeric AS historical_month_total,
                COALESCE(SUM(CASE WHEN h.day_of_month <= :cutoff_day THEN h.total ELSE 0 END), 0)::numeric AS historical_mtd_total,
                COALESCE(SUM(CASE WHEN h.day_of_month > :cutoff_day THEN h.total ELSE 0 END), 0)::numeric AS historical_remaining_total
            FROM historical h
            LEFT JOIN track_branch_catalog c
              ON upper(trim(c.sucursal_canon)) = h.sucursal_canon
            GROUP BY
                h.sucursal_canon,
                c.track_label,
                c.display_order
            """
        ).bindparams(
            bindparam("selected_branches", expanding=True),
            bindparam("excluded_branches", expanding=True),
        ),
        {
            "history_start_date": history_start_date,
            "history_end_date": history_end_date,
            "target_month_number": target_month.month,
            "cutoff_day": cutoff_day,
            "selected_branches": selected_branches,
            "excluded_branches": tuple(EXCLUDED_BRANCHES),
        },
    ).mappings().all()

    historical_by_branch = {
        str(row["sucursal_canon"]).strip().upper(): row
        for row in rows
    }

    items: list[dict[str, Any]] = []

    for sucursal_canon, real_row in real_by_branch.items():
        historical_row = historical_by_branch.get(sucursal_canon)

        historical_months = int(historical_row["historical_months"] or 0) if historical_row else 0
        historical_month_total = float(historical_row["historical_month_total"] or 0) if historical_row else 0.0
        historical_mtd_total = float(historical_row["historical_mtd_total"] or 0) if historical_row else 0.0
        historical_remaining_total = float(historical_row["historical_remaining_total"] or 0) if historical_row else 0.0

        historical_expected_mtd = None
        historical_expected_month_total = None
        historical_progress_pct = None
        gap = None
        gap_pct = None
        trend_factor = None
        projected_close = None

        if historical_months > 0:
            historical_expected_mtd = historical_mtd_total / historical_months
            historical_expected_month_total = historical_month_total / historical_months

        if historical_month_total > 0:
            historical_progress_pct = historical_mtd_total / historical_month_total

        real_mtd = float(real_row["real_mtd"] or 0)

        if historical_expected_mtd and historical_expected_mtd > 0:
            gap = real_mtd - historical_expected_mtd
            gap_pct = gap / historical_expected_mtd
            trend_factor = real_mtd / historical_expected_mtd

        if historical_progress_pct and historical_progress_pct > 0:
            projected_close = real_mtd / historical_progress_pct

        confidence = _confidence_from_comparable_months(historical_months)

        projection_quality_issue = _resolve_branch_projection_quality_issue(
            scope="branch",
            curve={
                "historical_months": historical_months,
                "historical_mtd_total": historical_mtd_total,
                "confidence": confidence,
            },
            trend_factor=trend_factor,
        )

        if projection_quality_issue:
            projected_close = None

        items.append({
            "sucursal_canon": sucursal_canon,
            "track_label": (
                str(historical_row["track_label"]).strip()
                if historical_row and historical_row["track_label"]
                else sucursal_canon
            ),
            "display_order": (
                int(historical_row["display_order"])
                if historical_row and historical_row["display_order"] is not None
                else None
            ),
            "real_mtd": real_mtd,
            "real_base_mtd": real_row["real_base_mtd"],
            "real_agregadora_mtd": real_row["real_agregadora_mtd"],
            "historical_months": historical_months,
            "historical_expected_mtd": historical_expected_mtd,
            "historical_expected_month_total": historical_expected_month_total,
            "historical_progress_pct": historical_progress_pct,
            "gap_vs_historical_expected": gap,
            "gap_vs_historical_expected_pct": gap_pct,
            "trend_factor": trend_factor,
            "projected_close": projected_close,
            "confidence": confidence,
            "projection_quality_issue": projection_quality_issue,
        })

    negative_gap_total = sum(
        abs(float(item["gap_vs_historical_expected"] or 0))
        for item in items
        if (item["gap_vs_historical_expected"] or 0) < 0
    )

    for item in items:
        gap = float(item["gap_vs_historical_expected"] or 0)

        item["impact_share_pct"] = (
            abs(gap) / negative_gap_total
            if gap < 0 and negative_gap_total > 0
            else 0.0
        )

    items = sorted(
        items,
        key=lambda item: (
            item["gap_vs_historical_expected"] is None,
            item["gap_vs_historical_expected"] if item["gap_vs_historical_expected"] is not None else 0,
            item["display_order"] is None,
            item["display_order"] or 9999,
            item["track_label"],
        ),
    )

    return {
        "status": "ok" if items else "empty",
        "scope": scope,
        "metric": "real_mtd_vs_historical_expected_mtd",
        "target_month": target_month.isoformat(),
        "cutoff_day": cutoff_day,
        "history_window": {
            "start": history_start_date.isoformat(),
            "end_exclusive": history_end_date.isoformat(),
        },
        "items_count": len(items),
        "negative_gap_total": negative_gap_total,
        "items": items,
    }


def _build_cohort_forecast(
    *,
    target_month: date,
    cutoff_day: int,
    scope: str,
    mart_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if scope != "national":
        return {
            "status": "not_applicable",
            "method": "legacy_21_plus_new_gyms",
            "scope": scope,
            "items": [],
        }

    history_start_date, history_end_date = _build_history_window(target_month)

    selected_branches = {
        str(row.get("sucursal_canon") or "").strip().upper()
        for row in mart_rows
        if str(row.get("sucursal_canon") or "").strip()
    }

    if not selected_branches:
        return {
            "status": "empty",
            "method": "legacy_21_plus_new_gyms",
            "scope": scope,
            "items": [],
        }

    cohort_lookup = build_track_branch_cohort_lookup(
        sucursales_canon=selected_branches,
        active_only=True,
    )

    definitions_by_key = {
        item["key"]: item
        for item in get_track_branch_cohort_definitions()
    }

    cohort_keys = [
        TRACK_BRANCH_COHORT_LEGACY_21,
        TRACK_BRANCH_COHORT_NEW_GYMS,
    ]

    cohort_accumulators: dict[str, dict[str, Any]] = {
        cohort_key: {
            "cohort_key": cohort_key,
            "label": definitions_by_key.get(cohort_key, {}).get("label", cohort_key),
            "real_mtd": 0.0,
            "real_base_mtd": 0.0,
            "real_agregadora_mtd": 0.0,
            "branches_count": 0,
            "branches": [],
            "history_by_month": {},
        }
        for cohort_key in cohort_keys
    }

    for row in mart_rows:
        sucursal_canon = str(row.get("sucursal_canon") or "").strip().upper()

        if not sucursal_canon:
            continue

        cohort_key = get_track_branch_cohort_key(
            sucursal_canon=sucursal_canon,
            cohort_lookup=cohort_lookup,
        )

        if cohort_key not in cohort_accumulators:
            continue

        accumulator = cohort_accumulators[cohort_key]

        accumulator["real_mtd"] += _to_float(row.get("real_mtd")) or 0.0
        accumulator["real_base_mtd"] += _to_float(row.get("ingreso_real_base_mtd")) or 0.0
        accumulator["real_agregadora_mtd"] += _to_float(row.get("ingreso_real_agregadora_mtd")) or 0.0
        accumulator["branches_count"] += 1
        accumulator["branches"].append(sucursal_canon)

    rows = db.session.execute(
        text(
            """
            WITH historical AS (
                SELECT
                    upper(trim(a.sucursal_canon)) AS sucursal_canon,
                    a.business_month,
                    a.day_of_month,
                    a.total
                FROM track_venta_total_daily_branch_agg a
                JOIN venta_total_snapshots s
                  ON s.id = a.snapshot_id
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND a.business_month >= :history_start_date
                  AND a.business_month < :history_end_date
                  AND EXTRACT(MONTH FROM a.business_month)::int = :target_month_number
                  AND upper(trim(a.sucursal_canon)) IN :selected_branches
                  AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
            )
            SELECT
                sucursal_canon,
                business_month,
                COALESCE(SUM(total), 0)::numeric AS month_total,
                COALESCE(SUM(CASE WHEN day_of_month <= :cutoff_day THEN total ELSE 0 END), 0)::numeric AS mtd_total,
                COALESCE(SUM(CASE WHEN day_of_month > :cutoff_day THEN total ELSE 0 END), 0)::numeric AS remaining_total
            FROM historical
            GROUP BY
                sucursal_canon,
                business_month
            """
        ).bindparams(
            bindparam("selected_branches", expanding=True),
            bindparam("excluded_branches", expanding=True),
        ),
        {
            "history_start_date": history_start_date,
            "history_end_date": history_end_date,
            "target_month_number": target_month.month,
            "cutoff_day": cutoff_day,
            "selected_branches": tuple(selected_branches),
            "excluded_branches": tuple(EXCLUDED_BRANCHES),
        },
    ).mappings().all()

    for row in rows:
        sucursal_canon = str(row["sucursal_canon"] or "").strip().upper()
        cohort_key = get_track_branch_cohort_key(
            sucursal_canon=sucursal_canon,
            cohort_lookup=cohort_lookup,
        )

        if cohort_key not in cohort_accumulators:
            continue

        business_month = row["business_month"]
        month_key = business_month.isoformat() if business_month else None

        if not month_key:
            continue

        history_by_month = cohort_accumulators[cohort_key]["history_by_month"]

        if month_key not in history_by_month:
            history_by_month[month_key] = {
                "business_month": month_key,
                "month_total": 0.0,
                "mtd_total": 0.0,
                "remaining_total": 0.0,
            }

        history_by_month[month_key]["month_total"] += float(row["month_total"] or 0)
        history_by_month[month_key]["mtd_total"] += float(row["mtd_total"] or 0)
        history_by_month[month_key]["remaining_total"] += float(row["remaining_total"] or 0)

    def build_item(cohort_key: str, accumulator: dict[str, Any]) -> dict[str, Any]:
        months = list(accumulator["history_by_month"].values())
        historical_months = len([
            month
            for month in months
            if float(month.get("month_total") or 0) > 0
        ])

        historical_month_total_aggregate = sum(float(month.get("month_total") or 0) for month in months)
        historical_mtd_total_aggregate = sum(float(month.get("mtd_total") or 0) for month in months)
        historical_remaining_total_aggregate = sum(float(month.get("remaining_total") or 0) for month in months)

        historical_expected_month_total = None
        historical_expected_mtd = None
        historical_expected_remaining = None
        historical_progress_pct = None
        trend_factor = None
        projected_close = None
        gap_vs_expected_mtd = None
        gap_vs_expected_mtd_pct = None

        if historical_months > 0:
            historical_expected_month_total = historical_month_total_aggregate / historical_months
            historical_expected_mtd = historical_mtd_total_aggregate / historical_months
            historical_expected_remaining = historical_remaining_total_aggregate / historical_months

        if historical_month_total_aggregate > 0:
            historical_progress_pct = historical_mtd_total_aggregate / historical_month_total_aggregate

        real_mtd = float(accumulator["real_mtd"] or 0)

        if historical_expected_mtd and historical_expected_mtd > 0:
            trend_factor = real_mtd / historical_expected_mtd
            gap_vs_expected_mtd = real_mtd - historical_expected_mtd
            gap_vs_expected_mtd_pct = gap_vs_expected_mtd / historical_expected_mtd

        if historical_progress_pct and historical_progress_pct > 0:
            projected_close = real_mtd / historical_progress_pct

        confidence = _confidence_from_comparable_months(historical_months)

        projected_close_experimental = projected_close
        projection_quality_issue = None
        quality_reasons: list[str] = []

        if historical_months < 3:
            quality_reasons.append("La cohorte tiene menos de 3 meses comparables para este mes.")

        if confidence != "alta":
            quality_reasons.append(f"La confianza histórica de la cohorte es {confidence}.")

        if historical_expected_mtd is None or historical_expected_mtd < 50000:
            quality_reasons.append("El promedio histórico esperado MTD de la cohorte es demasiado bajo para proyectar con estabilidad.")

        if trend_factor is not None and trend_factor > 3:
            quality_reasons.append("El factor de tendencia de la cohorte es extremo contra su histórico esperado.")

        if quality_reasons:
            projection_quality_issue = {
                "code": "insufficient_cohort_history",
                "severity": "warning",
                "message": "Histórico insuficiente para proyectar esta cohorte con estabilidad.",
                "reasons": quality_reasons,
                "thresholds": {
                    "min_historical_months": 3,
                    "min_historical_expected_mtd": 50000,
                    "max_trend_factor": 3,
                },
            }
            projected_close = None

        return {
            "cohort_key": cohort_key,
            "label": accumulator["label"],
            "branches_count": int(accumulator["branches_count"] or 0),
            "branches": sorted(accumulator["branches"]),
            "real_mtd": real_mtd,
            "real_base_mtd": float(accumulator["real_base_mtd"] or 0),
            "real_agregadora_mtd": float(accumulator["real_agregadora_mtd"] or 0),
            "historical_months": historical_months,
            "historical_expected_mtd": historical_expected_mtd,
            "historical_expected_remaining": historical_expected_remaining,
            "historical_expected_month_total": historical_expected_month_total,
            "historical_progress_pct": historical_progress_pct,
            "trend_factor": trend_factor,
            "gap_vs_expected_mtd": gap_vs_expected_mtd,
            "gap_vs_expected_mtd_pct": gap_vs_expected_mtd_pct,
            "projected_close": projected_close,
            "projected_close_experimental": projected_close_experimental,
            "confidence": confidence,
            "projection_quality_issue": projection_quality_issue,
            "history_months": sorted(months, key=lambda month: month["business_month"]),
        }

    items = [
        build_item(cohort_key, cohort_accumulators[cohort_key])
        for cohort_key in cohort_keys
    ]

    component_quality_issues = [
        item
        for item in items
        if item.get("projection_quality_issue") or item.get("projected_close") is None
    ]

    total_projected_close_experimental = sum(
        float(
            item.get("projected_close_experimental")
            if item.get("projected_close_experimental") is not None
            else item.get("projected_close") or 0
        )
        for item in items
    )

    total_projected_close = (
        None
        if component_quality_issues
        else sum(float(item.get("projected_close") or 0) for item in items)
    )

    total_projection_quality_issue = None

    if component_quality_issues:
        total_projection_quality_issue = {
            "code": "partial_cohort_history",
            "severity": "warning",
            "message": "No se puede consolidar una proyección confiable por cohortes porque una o más cohortes tienen histórico insuficiente.",
            "reasons": [
                (
                    f"{item.get('label')}: "
                    f"{(item.get('projection_quality_issue') or {}).get('message', 'Sin proyección estable.')}"
                )
                for item in component_quality_issues
            ],
        }

    total_item = {
        "cohort_key": TRACK_BRANCH_COHORT_TOTAL_ULTRA,
        "label": definitions_by_key.get(TRACK_BRANCH_COHORT_TOTAL_ULTRA, {}).get("label", "ULTRA TOTAL"),
        "branches_count": sum(int(item["branches_count"] or 0) for item in items),
        "branches": sorted({
            branch
            for item in items
            for branch in item.get("branches", [])
        }),
        "real_mtd": sum(float(item["real_mtd"] or 0) for item in items),
        "real_base_mtd": sum(float(item["real_base_mtd"] or 0) for item in items),
        "real_agregadora_mtd": sum(float(item["real_agregadora_mtd"] or 0) for item in items),
        "historical_months": None,
        "historical_expected_mtd": sum(float(item["historical_expected_mtd"] or 0) for item in items),
        "historical_expected_remaining": sum(float(item["historical_expected_remaining"] or 0) for item in items),
        "historical_expected_month_total": sum(float(item["historical_expected_month_total"] or 0) for item in items),
        "historical_progress_pct": None,
        "trend_factor": None,
        "gap_vs_expected_mtd": None,
        "gap_vs_expected_mtd_pct": None,
        "projected_close": total_projected_close,
        "projected_close_experimental": total_projected_close_experimental,
        "confidence": "mixta",
        "projection_quality_issue": total_projection_quality_issue,
        "history_months": [],
    }

    if total_item["historical_expected_mtd"] and total_item["historical_expected_mtd"] > 0:
        total_item["trend_factor"] = total_item["real_mtd"] / total_item["historical_expected_mtd"]
        total_item["gap_vs_expected_mtd"] = total_item["real_mtd"] - total_item["historical_expected_mtd"]
        total_item["gap_vs_expected_mtd_pct"] = total_item["gap_vs_expected_mtd"] / total_item["historical_expected_mtd"]

    if total_item["historical_expected_month_total"] and total_item["historical_expected_month_total"] > 0:
        total_item["historical_progress_pct"] = (
            total_item["historical_expected_mtd"] / total_item["historical_expected_month_total"]
        )

    all_items = [total_item] + items

    return {
        "status": "ok",
        "method": "legacy_21_plus_new_gyms",
        "scope": scope,
        "target_month": target_month.isoformat(),
        "cutoff_day": cutoff_day,
        "history_window": {
            "start": history_start_date.isoformat(),
            "end_exclusive": history_end_date.isoformat(),
        },
        "items": all_items,
    }


def _first_day_previous_month(value: date) -> date:
    if value.month == 1:
        return date(value.year - 1, 12, 1)

    return date(value.year, value.month - 1, 1)


def _build_anchored_remaining_forecast(
    *,
    target_month: date,
    cutoff_day: int,
    scope: str,
    mart_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if scope != "national":
        return {
            "status": "not_applicable",
            "method": "previous_close_plus_expected_remaining",
            "scope": scope,
            "items": [],
        }

    previous_month = _first_day_previous_month(target_month)
    previous_month_end = target_month - timedelta(days=1)

    selected_branches = {
        str(row.get("sucursal_canon") or "").strip().upper()
        for row in mart_rows
        if str(row.get("sucursal_canon") or "").strip()
    }

    if not selected_branches:
        return {
            "status": "empty",
            "method": "previous_close_plus_expected_remaining",
            "scope": scope,
            "items": [],
        }

    cohort_lookup = build_track_branch_cohort_lookup(
        sucursales_canon=selected_branches,
        active_only=True,
    )

    definitions_by_key = {
        item["key"]: item
        for item in get_track_branch_cohort_definitions()
    }

    cohort_keys = [
        TRACK_BRANCH_COHORT_LEGACY_21,
        TRACK_BRANCH_COHORT_NEW_GYMS,
    ]

    current_by_cohort: dict[str, dict[str, Any]] = {
        cohort_key: {
            "cohort_key": cohort_key,
            "label": definitions_by_key.get(cohort_key, {}).get("label", cohort_key),
            "branches_count": 0,
            "branches": [],
            "current_base_mtd": 0.0,
            "current_agregadora_mtd": 0.0,
            "current_total_mtd": 0.0,
        }
        for cohort_key in cohort_keys
    }

    for row in mart_rows:
        sucursal_canon = str(row.get("sucursal_canon") or "").strip().upper()

        if not sucursal_canon:
            continue

        cohort_key = get_track_branch_cohort_key(
            sucursal_canon=sucursal_canon,
            cohort_lookup=cohort_lookup,
        )

        if cohort_key not in current_by_cohort:
            continue

        base_mtd = _to_float(row.get("ingreso_real_base_mtd")) or 0.0
        agregadora_mtd = _to_float(row.get("ingreso_real_agregadora_mtd")) or 0.0

        total_mtd = (
            _to_float(row.get("ingreso_real_total_mtd"))
            or _to_float(row.get("ingreso_real_mtd"))
            or _to_float(row.get("real_mtd"))
            or (base_mtd + agregadora_mtd)
        )

        accumulator = current_by_cohort[cohort_key]
        accumulator["branches_count"] += 1
        accumulator["branches"].append(sucursal_canon)
        accumulator["current_base_mtd"] += base_mtd
        accumulator["current_agregadora_mtd"] += agregadora_mtd
        accumulator["current_total_mtd"] += total_mtd

    previous_closed_rows = db.session.execute(
        text(
            """
            WITH selected_version AS (
                SELECT id
                FROM track_daily_versions
                WHERE track_date = :previous_month_end
                  AND version_type = 'cierre_canonico'
                  AND status = 'success'
                ORDER BY is_current DESC, id DESC
                LIMIT 1
            ),
            branch_rows AS (
                SELECT
                    CASE
                        WHEN c.display_order <= 21 THEN 'legacy_21'
                        ELSE 'new_gyms'
                    END AS cohort_key,
                    CASE
                        WHEN c.display_order <= 21 THEN 'ULTRA 21 GYMS'
                        ELSE 'ULTRA NUEVOS'
                    END AS cohort_label,
                    COALESCE(m.ingreso_real_base_mtd, 0)::numeric AS base_total,
                    COALESCE(m.ingreso_real_agregadora_mtd, 0)::numeric AS agregadora_total,
                    COALESCE(
                        m.ingreso_real_total_mtd,
                        m.ingreso_real_mtd,
                        COALESCE(m.ingreso_real_base_mtd, 0) + COALESCE(m.ingreso_real_agregadora_mtd, 0),
                        0
                    )::numeric AS total
                FROM selected_version v
                JOIN track_daily_mart m
                  ON m.track_daily_version_id = v.id
                JOIN track_branch_catalog c
                  ON upper(trim(c.sucursal_canon)) = upper(trim(m.sucursal_canon))
                WHERE c.is_track_active = true
                  AND upper(trim(m.sucursal_canon)) NOT IN :excluded_branches
            )
            SELECT
                cohort_key,
                cohort_label,
                COUNT(*)::int AS branches_count,
                SUM(base_total)::numeric AS previous_base_total,
                SUM(agregadora_total)::numeric AS previous_agregadora_total,
                SUM(total)::numeric AS previous_closed_total
            FROM branch_rows
            GROUP BY cohort_key, cohort_label
            """
        ).bindparams(
            bindparam("excluded_branches", expanding=True),
        ),
        {
            "previous_month_end": previous_month_end,
            "excluded_branches": tuple(EXCLUDED_BRANCHES),
        },
    ).mappings().all()

    previous_by_cohort = {
        str(row["cohort_key"]): dict(row)
        for row in previous_closed_rows
    }

    history_start = _first_day_previous_month(
        date(target_month.year - 3, target_month.month, 1)
    )

    history_rows = db.session.execute(
        text(
            """
            WITH latest_month_snapshot AS (
                SELECT DISTINCT ON (date_trunc('month', s.business_date)::date)
                    s.id AS snapshot_id,
                    date_trunc('month', s.business_date)::date AS business_month,
                    s.business_date
                FROM venta_total_snapshots s
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND date_trunc('month', s.business_date)::date >= :history_start
                  AND date_trunc('month', s.business_date)::date < :target_month
                ORDER BY
                    date_trunc('month', s.business_date)::date,
                    s.business_date DESC,
                    s.id DESC
            ),
            branch_daily AS (
                SELECT
                    l.business_month,
                    a.day_of_month,
                    CASE
                        WHEN c.display_order <= 21 THEN 'legacy_21'
                        ELSE 'new_gyms'
                    END AS cohort_key,
                    SUM(a.total)::numeric AS daily_total
                FROM latest_month_snapshot l
                JOIN track_venta_total_daily_branch_agg a
                  ON a.snapshot_id = l.snapshot_id
                JOIN track_branch_catalog c
                  ON upper(trim(c.sucursal_canon)) = upper(trim(a.sucursal_canon))
                WHERE c.is_track_active = true
                  AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
                GROUP BY
                    l.business_month,
                    a.day_of_month,
                    CASE WHEN c.display_order <= 21 THEN 'legacy_21' ELSE 'new_gyms' END
            )
            SELECT
                business_month,
                day_of_month,
                cohort_key,
                SUM(daily_total)::numeric AS daily_total
            FROM branch_daily
            GROUP BY
                business_month,
                day_of_month,
                cohort_key
            ORDER BY
                cohort_key,
                business_month,
                day_of_month
            """
        ).bindparams(
            bindparam("excluded_branches", expanding=True),
        ),
        {
            "history_start": history_start,
            "target_month": target_month,
            "excluded_branches": tuple(EXCLUDED_BRANCHES),
        },
    ).mappings().all()

    monthly_daily: dict[tuple[str, date], dict[int, float]] = {}

    for row in history_rows:
        cohort_key = str(row["cohort_key"])
        business_month = row["business_month"]
        day_of_month = int(row["day_of_month"] or 0)

        if not business_month or not day_of_month:
            continue

        key = (cohort_key, business_month)
        monthly_daily.setdefault(key, {})
        monthly_daily[key][day_of_month] = monthly_daily[key].get(day_of_month, 0.0) + float(row["daily_total"] or 0)

    monthly_totals = {
        key: sum(days.values())
        for key, days in monthly_daily.items()
    }

    def build_seasonal_factor(cohort_key: str) -> tuple[float | None, int, list[dict[str, Any]]]:
        samples: list[dict[str, Any]] = []

        for (sample_cohort_key, business_month), month_total in monthly_totals.items():
            if sample_cohort_key != cohort_key:
                continue

            if business_month.month != target_month.month:
                continue

            if month_total <= 0:
                continue

            sample_previous_month = _first_day_previous_month(business_month)
            previous_total = monthly_totals.get((cohort_key, sample_previous_month))

            if not previous_total or previous_total <= 0:
                continue

            factor = month_total / previous_total

            samples.append({
                "year": business_month.year,
                "business_month": business_month.isoformat(),
                "previous_month": sample_previous_month.isoformat(),
                "previous_total": previous_total,
                "month_total": month_total,
                "factor": factor,
            })

        if not samples:
            return None, 0, []

        factors = [float(item["factor"] or 0) for item in samples if item.get("factor") is not None]

        if not factors:
            return None, 0, samples

        return sum(factors) / len(factors), len(factors), samples

    def build_expected_cumulative_pct(cohort_key: str) -> tuple[float | None, int, str, list[dict[str, Any]]]:
        samples: list[dict[str, Any]] = []

        for (sample_cohort_key, business_month), month_total in monthly_totals.items():
            if sample_cohort_key != cohort_key:
                continue

            if month_total <= 0:
                continue

            if cohort_key == TRACK_BRANCH_COHORT_LEGACY_21 and business_month.month != target_month.month:
                continue

            days = monthly_daily.get((sample_cohort_key, business_month), {})
            mtd_total = sum(
                value
                for day, value in days.items()
                if day <= cutoff_day
            )

            if mtd_total <= 0:
                continue

            samples.append({
                "year": business_month.year,
                "business_month": business_month.isoformat(),
                "mtd_total": mtd_total,
                "month_total": month_total,
                "cumulative_pct": mtd_total / month_total,
            })

        method = (
            "same_month_history"
            if cohort_key == TRACK_BRANCH_COHORT_LEGACY_21
            else "recent_available_history"
        )

        if not samples:
            return None, 0, method, []

        cumulative_values = [
            float(item["cumulative_pct"] or 0)
            for item in samples
            if item.get("cumulative_pct") is not None
        ]

        if not cumulative_values:
            return None, 0, method, samples

        return sum(cumulative_values) / len(cumulative_values), len(cumulative_values), method, samples

    def build_item(cohort_key: str) -> dict[str, Any]:
        current = current_by_cohort.get(cohort_key) or {}
        previous = previous_by_cohort.get(cohort_key) or {}

        label = (
            current.get("label")
            or previous.get("cohort_label")
            or definitions_by_key.get(cohort_key, {}).get("label")
            or cohort_key
        )

        current_total_mtd = float(current.get("current_total_mtd") or 0)
        previous_closed_total = _to_float(previous.get("previous_closed_total"))

        seasonal_factor, seasonal_years, seasonal_samples = build_seasonal_factor(cohort_key)
        expected_cumulative_pct, cumulative_years, cumulative_method, cumulative_samples = build_expected_cumulative_pct(cohort_key)

        seasonal_factor_applied = seasonal_factor
        seasonal_factor_source = "same_month_historical_factor"

        if cohort_key == TRACK_BRANCH_COHORT_NEW_GYMS:
            seasonal_factor_applied = 1.0
            seasonal_factor_source = "previous_close_no_seasonal_factor"

        expected_close_before_cutoff = None
        expected_mtd_at_cutoff = None
        expected_remaining = None
        projected_close = None
        gap_vs_expected_mtd = None
        gap_vs_expected_mtd_pct = None

        if previous_closed_total and seasonal_factor_applied:
            expected_close_before_cutoff = previous_closed_total * seasonal_factor_applied

        if expected_close_before_cutoff and expected_cumulative_pct:
            expected_mtd_at_cutoff = expected_close_before_cutoff * expected_cumulative_pct
            expected_remaining = expected_close_before_cutoff - expected_mtd_at_cutoff
            projected_close = current_total_mtd + expected_remaining
            gap_vs_expected_mtd = current_total_mtd - expected_mtd_at_cutoff

            if expected_mtd_at_cutoff > 0:
                gap_vs_expected_mtd_pct = gap_vs_expected_mtd / expected_mtd_at_cutoff

        confidence = "alta"

        if cohort_key == TRACK_BRANCH_COHORT_NEW_GYMS:
            confidence = "media" if cumulative_years >= 6 else "baja"
        elif seasonal_years < 3 or cumulative_years < 3:
            confidence = "media"

        quality_issue = None
        quality_reasons: list[str] = []

        if not previous_closed_total:
            quality_reasons.append("No existe cierre canónico del mes anterior para esta cohorte.")

        if expected_cumulative_pct is None:
            quality_reasons.append("No existe curva acumulada histórica usable para esta cohorte.")

        if cohort_key == TRACK_BRANCH_COHORT_LEGACY_21 and seasonal_factor is None:
            quality_reasons.append("No existe factor estacional histórico usable para ULTRA 21 GYMS.")

        if quality_reasons:
            quality_issue = {
                "code": "insufficient_anchor_history",
                "severity": "warning",
                "message": "No se puede calcular proyección anclada estable para esta cohorte.",
                "reasons": quality_reasons,
            }
            projected_close = None

        return {
            "cohort_key": cohort_key,
            "label": label,
            "branches_count": int(current.get("branches_count") or previous.get("branches_count") or 0),
            "branches": sorted(current.get("branches") or []),
            "current_base_mtd": float(current.get("current_base_mtd") or 0),
            "current_agregadora_mtd": float(current.get("current_agregadora_mtd") or 0),
            "current_total_mtd": current_total_mtd,
            "previous_base_total": _to_float(previous.get("previous_base_total")),
            "previous_agregadora_total": _to_float(previous.get("previous_agregadora_total")),
            "previous_closed_total": previous_closed_total,
            "seasonal_factor": seasonal_factor,
            "seasonal_factor_applied": seasonal_factor_applied,
            "seasonal_factor_source": seasonal_factor_source,
            "seasonal_years": seasonal_years,
            "expected_cumulative_pct": expected_cumulative_pct,
            "expected_cumulative_method": cumulative_method,
            "cumulative_years": cumulative_years,
            "expected_close_before_cutoff": expected_close_before_cutoff,
            "expected_mtd_at_cutoff": expected_mtd_at_cutoff,
            "expected_remaining": expected_remaining,
            "gap_vs_expected_mtd": gap_vs_expected_mtd,
            "gap_vs_expected_mtd_pct": gap_vs_expected_mtd_pct,
            "projected_close": projected_close,
            "confidence": confidence,
            "projection_quality_issue": quality_issue,
            "seasonal_samples": seasonal_samples,
            "cumulative_samples": cumulative_samples,
        }

    items = [
        build_item(cohort_key)
        for cohort_key in cohort_keys
    ]

    total_projected_close = (
        None
        if any(item.get("projected_close") is None for item in items)
        else sum(float(item.get("projected_close") or 0) for item in items)
    )

    total_quality_issue = None

    if total_projected_close is None:
        total_quality_issue = {
            "code": "partial_anchor_history",
            "severity": "warning",
            "message": "No se puede consolidar una proyección anclada estable porque una o más cohortes no tienen datos suficientes.",
        }

    total_item = {
        "cohort_key": TRACK_BRANCH_COHORT_TOTAL_ULTRA,
        "label": definitions_by_key.get(TRACK_BRANCH_COHORT_TOTAL_ULTRA, {}).get("label", "ULTRA GYM"),
        "branches_count": sum(int(item.get("branches_count") or 0) for item in items),
        "branches": sorted({
            branch
            for item in items
            for branch in item.get("branches", [])
        }),
        "current_base_mtd": sum(float(item.get("current_base_mtd") or 0) for item in items),
        "current_agregadora_mtd": sum(float(item.get("current_agregadora_mtd") or 0) for item in items),
        "current_total_mtd": sum(float(item.get("current_total_mtd") or 0) for item in items),
        "previous_base_total": sum(float(item.get("previous_base_total") or 0) for item in items),
        "previous_agregadora_total": sum(float(item.get("previous_agregadora_total") or 0) for item in items),
        "previous_closed_total": sum(float(item.get("previous_closed_total") or 0) for item in items),
        "seasonal_factor": None,
        "seasonal_factor_applied": None,
        "seasonal_factor_source": "sum_of_cohorts",
        "seasonal_years": None,
        "expected_cumulative_pct": None,
        "expected_cumulative_method": "sum_of_cohorts",
        "cumulative_years": None,
        "expected_close_before_cutoff": sum(float(item.get("expected_close_before_cutoff") or 0) for item in items),
        "expected_mtd_at_cutoff": sum(float(item.get("expected_mtd_at_cutoff") or 0) for item in items),
        "expected_remaining": sum(float(item.get("expected_remaining") or 0) for item in items),
        "gap_vs_expected_mtd": sum(float(item.get("gap_vs_expected_mtd") or 0) for item in items),
        "gap_vs_expected_mtd_pct": None,
        "projected_close": total_projected_close,
        "confidence": "mixta",
        "projection_quality_issue": total_quality_issue,
        "seasonal_samples": [],
        "cumulative_samples": [],
    }

    if total_item["expected_mtd_at_cutoff"]:
        total_item["gap_vs_expected_mtd_pct"] = (
            total_item["gap_vs_expected_mtd"] / total_item["expected_mtd_at_cutoff"]
        )

    return {
        "status": "ok",
        "method": "previous_close_plus_expected_remaining",
        "scope": scope,
        "target_month": target_month.isoformat(),
        "cutoff_day": cutoff_day,
        "previous_month": previous_month.isoformat(),
        "previous_month_end": previous_month_end.isoformat(),
        "items": [total_item] + items,
    }

def build_venta_total_forecast(
    *,
    track_date: date,
    generation_mode: str,
    track_daily_version_id: int,
    scope: str = "national",
    branch: str | None = None,
) -> dict[str, Any]:
    scope = (scope or "national").strip().lower()

    if scope not in {"national", "branch"}:
        raise ValueError("scope inválido. Usa national o branch.")

    target_month = _first_day_of_month(track_date)
    cutoff_day = min(track_date.day, monthrange(track_date.year, track_date.month)[1])
    history_start_date, history_end_date = _build_history_window(target_month)

    mart_rows = _get_selected_mart_rows(
        track_daily_version_id=track_daily_version_id,
        scope=scope,
        branch=branch,
    )

    if scope == "branch" and not mart_rows:
        raise ValueError(f"No existe fila Track para branch={branch!r} en la versión resuelta.")

    selected_branches = [str(row["sucursal_canon"]) for row in mart_rows]

    real_mtd = sum((_to_float(row["real_mtd"]) or 0.0) for row in mart_rows)
    real_base_mtd = sum((_to_float(row["ingreso_real_base_mtd"]) or 0.0) for row in mart_rows)
    real_agregadora_mtd = sum((_to_float(row["ingreso_real_agregadora_mtd"]) or 0.0) for row in mart_rows)

    mart_goal_available_count = sum(1 for row in mart_rows if row.get("meta_faycgo_mes") is not None)
    mart_goal_total = sum((_to_float(row["meta_faycgo_mes"]) or 0.0) for row in mart_rows)

    expected_goal_count = len(mart_rows)
    goal_status = _goal_status_from_count(
        expected_count=expected_goal_count,
        available_count=mart_goal_available_count,
    )

    goal_month: float | None = None

    if goal_status == "available":
        goal_month = mart_goal_total
    else:
        fallback_goal, fallback_available_count = _resolve_goal_from_track_monthly_targets(
            target_month=target_month,
            selected_branches=selected_branches,
        )

        fallback_status = _goal_status_from_count(
            expected_count=expected_goal_count,
            available_count=fallback_available_count,
        )

        if fallback_status == "available":
            goal_status = "available"
            goal_month = fallback_goal
        elif fallback_status == "partial":
            goal_status = "partial"
            goal_month = None
        else:
            goal_status = "pending"
            goal_month = None

    curve = _build_historical_curve(
        target_month=target_month,
        cutoff_day=cutoff_day,
        scope=scope,
        branch=branch,
    )

    progress_pct = curve["historical_progress_pct"]
    historical_months = int(curve.get("historical_months") or 0)

    historical_expected_mtd = None
    historical_expected_remaining = None
    historical_expected_month_total = None

    if historical_months > 0:
        historical_expected_mtd = curve["historical_mtd_total"] / historical_months
        historical_expected_remaining = curve["historical_remaining_total"] / historical_months
        historical_expected_month_total = curve["historical_month_total"] / historical_months

    projected_close = None
    trend_factor = None
    weighted_goal_mtd = None
    gap_vs_weighted_goal = None
    gap_vs_weighted_goal_pct = None
    status_vs_goal = None

    if progress_pct and progress_pct > 0:
        projected_close = real_mtd / progress_pct

        if historical_expected_mtd and historical_expected_mtd > 0:
            trend_factor = real_mtd / historical_expected_mtd

        if goal_status == "available" and goal_month is not None:
            weighted_goal_mtd = goal_month * progress_pct
            gap_vs_weighted_goal = real_mtd - weighted_goal_mtd

            if weighted_goal_mtd > 0:
                gap_vs_weighted_goal_pct = gap_vs_weighted_goal / weighted_goal_mtd

            status_vs_goal = _status_vs_goal(
                gap_pct=gap_vs_weighted_goal_pct,
                progress_pct=progress_pct,
            )

    branch_projection_quality_issue = _resolve_branch_projection_quality_issue(
        scope=scope,
        curve=curve,
        trend_factor=trend_factor,
    )

    if branch_projection_quality_issue:
        projected_close = None
        weighted_goal_mtd = None
        gap_vs_weighted_goal = None
        gap_vs_weighted_goal_pct = None
        status_vs_goal = None

    coverage = _build_history_coverage(
        target_month=target_month,
        branch=branch if scope == "branch" else None,
    )

    confidence = coverage["confidence"] if scope == "branch" else curve["confidence"]
    goal_status_message = _goal_status_message(goal_status)

    canonical_cutoff = _resolve_aggregated_canonical_cutoff(
        target_month=target_month,
        track_date=track_date,
        scope=scope,
        branch=branch,
    )

    forecast_cutoff = _build_forecast_cutoff(
        track_date=track_date,
        target_month=target_month,
        cutoff_day=cutoff_day,
        generation_mode=generation_mode,
        canonical_cutoff=canonical_cutoff,
    )

    executive_status = _build_executive_status(
        projected_close=projected_close,
        trend_factor=trend_factor,
        goal_status=goal_status,
        gap_vs_weighted_goal_pct=gap_vs_weighted_goal_pct,
        branch_projection_quality_issue=branch_projection_quality_issue,
    )

    forecast_explanation = _build_forecast_explanation(
        cutoff_day=cutoff_day,
        real_mtd=real_mtd,
        projected_close=projected_close,
        progress_pct=progress_pct,
        historical_mtd_total=historical_expected_mtd,
        trend_factor=trend_factor,
    )

    same_day_history = _build_same_day_history(
        target_month=target_month,
        cutoff_day=cutoff_day,
        scope=scope,
        branch=branch,
        real_mtd=real_mtd,
        projected_close=projected_close,
        progress_pct=progress_pct,
        trend_factor=trend_factor,
    )

    branch_drivers = _build_branch_drivers(
        target_month=target_month,
        cutoff_day=cutoff_day,
        scope=scope,
        mart_rows=mart_rows,
    )

    cohort_forecast = _build_cohort_forecast(
        target_month=target_month,
        cutoff_day=cutoff_day,
        scope=scope,
        mart_rows=mart_rows,
    )

    anchored_remaining_forecast = _build_anchored_remaining_forecast(
        target_month=target_month,
        cutoff_day=cutoff_day,
        scope=scope,
        mart_rows=mart_rows,
    )

    warnings = _build_forecast_warnings(
        generation_mode=generation_mode,
        goal_status=goal_status,
        curve=curve,
        canonical_cutoff=canonical_cutoff,
        branch_projection_quality_issue=branch_projection_quality_issue,
    )

    return {
        "status": "ok",
        "metadata": {
            "track_date": track_date.isoformat(),
            "target_month": target_month.isoformat(),
            "generation_mode": generation_mode,
            "track_daily_version_id": track_daily_version_id,
            "scope": scope,
            "branch": branch.strip().upper() if branch else None,
            "selected_branches_count": len(selected_branches),
            "excluded_branches": sorted(EXCLUDED_BRANCHES),
            "history_window": {
                "start": history_start_date.isoformat(),
                "end_exclusive": history_end_date.isoformat(),
            },
        },
        "forecast_cutoff": forecast_cutoff,
        "executive_status": executive_status,
        "forecast_explanation": forecast_explanation,
        "same_day_history": same_day_history,
        "branch_drivers": branch_drivers,
        "cohort_forecast": cohort_forecast,
        "anchored_remaining_forecast": anchored_remaining_forecast,
        "warnings": warnings,
        "data_quality": {
            "goal_status": goal_status,
            "goal_status_message": goal_status_message,
            "history_coverage": coverage,
            "branch_projection_quality_issue": branch_projection_quality_issue,
        },
        "summary": {
            "real_mtd": real_mtd,
            "real_base_mtd": real_base_mtd,
            "real_agregadora_mtd": real_agregadora_mtd,
            "goal_month": goal_month,
            "historical_progress_pct": progress_pct,
            "historical_expected_mtd": historical_expected_mtd,
            "historical_expected_remaining": historical_expected_remaining,
            "historical_expected_month_total": historical_expected_month_total,
            "historical_expected_mtd_aggregate": curve["historical_mtd_total"],
            "historical_expected_remaining_aggregate": curve["historical_remaining_total"],
            "historical_expected_month_total_aggregate": curve["historical_month_total"],
            "trend_factor_raw": trend_factor,
            "projected_close": projected_close,
            "weighted_goal_mtd": weighted_goal_mtd,
            "gap_vs_weighted_goal": gap_vs_weighted_goal,
            "gap_vs_weighted_goal_pct": gap_vs_weighted_goal_pct,
            "status_vs_goal": status_vs_goal,
            "confidence": confidence,
        },
        "historical_curve": curve,
    }


def _detail_decimal(value: Any, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise BranchForecastDetailConsistencyError(
            f"{field_name} contiene un valor booleano inesperado."
        )
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise BranchForecastDetailConsistencyError(
            f"{field_name} no contiene un valor numérico válido."
        ) from exc


def _require_detail_match(
    *,
    actual: Any,
    expected: Any,
    field_name: str,
    tolerance: Decimal = Decimal("0.000000001"),
) -> None:
    actual_decimal = _detail_decimal(actual, field_name=f"{field_name}.actual")
    expected_decimal = _detail_decimal(
        expected,
        field_name=f"{field_name}.expected",
    )
    if actual_decimal is None or expected_decimal is None:
        if actual_decimal is expected_decimal:
            return
        raise BranchForecastDetailConsistencyError(
            f"Inconsistencia en {field_name}: uno de los valores es nulo."
        )
    if abs(actual_decimal - expected_decimal) > tolerance:
        raise BranchForecastDetailConsistencyError(
            f"Inconsistencia en {field_name}: el detalle no coincide con el forecast base."
        )


def _build_branch_goal_pace_detail(
    *,
    goal_status: str,
    goal_month: Decimal | None,
    real_mtd_at_cutoff: Decimal | None,
    projected_close: Decimal | None,
    target_month: date,
    cutoff_day: int,
    historical_expected: BranchHistoricalExpectedCurve,
    calendar_aligned_distribution: BranchCalendarAlignedDistribution,
) -> BranchGoalPaceDetail:
    target_month = target_month.replace(day=1)
    days_in_target_month = monthrange(target_month.year, target_month.month)[1]
    remaining_days = days_in_target_month - min(
        max(cutoff_day, 0),
        days_in_target_month,
    )
    comparability_note = (
        "La distribución diaria se deriva del patrón histórico de venta base "
        "y se aplica a la meta total, incluidas agregadoras."
    )

    result: BranchGoalPaceDetail = {
        "status": "invalid_goal",
        "metric_basis": "total_mtd",
        "goal_metric_basis": "total_mtd",
        "distribution_basis": "venta_total_base",
        "method": "goal_month_by_weekday_ordinal_aligned_historical_weights",
        "includes_agregadoras": True,
        "aggregadoras_assumed_same_daily_shape": True,
        "comparability_note": comparability_note,
        "goal_month": goal_month,
        "goal_expected_mtd_at_cutoff": None,
        "real_mtd_at_cutoff": real_mtd_at_cutoff,
        "gap_vs_goal_pace": None,
        "gap_vs_goal_pace_pct": None,
        "remaining_to_goal": None,
        "remaining_days": remaining_days,
        "required_daily_average": None,
        "projected_close": projected_close,
        "projected_gap_to_goal": None,
        "projected_goal_attainment_pct": None,
        "points": [],
        "projected_path": None,
    }

    if goal_status == "pending":
        result["status"] = "no_goal"
        return result
    if goal_status == "partial":
        result["status"] = "partial_goal"
        return result
    if goal_month is None or not goal_month.is_finite():
        if goal_month is not None:
            result["goal_month"] = None
        return result
    if goal_month <= 0:
        progress_at_cutoff = calendar_aligned_distribution[
            "historical_progress_pct_at_cutoff"
        ]
        if (
            real_mtd_at_cutoff is not None
            and real_mtd_at_cutoff.is_finite()
            and calendar_aligned_distribution["status"]
            in ("available", "available_with_fallback")
            and progress_at_cutoff is not None
            and progress_at_cutoff.is_finite()
        ):
            goal_expected_mtd_at_cutoff = goal_month * progress_at_cutoff
            result["goal_expected_mtd_at_cutoff"] = (
                goal_expected_mtd_at_cutoff
            )
            result["gap_vs_goal_pace"] = (
                real_mtd_at_cutoff - goal_expected_mtd_at_cutoff
            )
        return result
    if (
        real_mtd_at_cutoff is None
        or not real_mtd_at_cutoff.is_finite()
    ):
        raise BranchForecastDetailConsistencyError(
            "summary.real_mtd no contiene un valor finito para goal_pace."
        )
    if projected_close is not None and not projected_close.is_finite():
        raise BranchForecastDetailConsistencyError(
            "summary.projected_close no contiene un valor finito para goal_pace."
        )

    remaining_to_goal = max(
        goal_month - real_mtd_at_cutoff,
        Decimal("0"),
    )
    required_daily_average = None
    if remaining_to_goal == 0:
        required_daily_average = Decimal("0")
    elif remaining_days > 0:
        required_daily_average = remaining_to_goal / Decimal(remaining_days)
    result["remaining_to_goal"] = remaining_to_goal
    result["required_daily_average"] = required_daily_average

    if (
        historical_expected["status"] != "available"
        or not historical_expected["points"]
        or calendar_aligned_distribution["status"]
        not in ("available", "available_with_fallback")
        or not calendar_aligned_distribution["points"]
    ):
        result["status"] = "historical_curve_unavailable"
        return result

    points: list[BranchGoalPacePoint] = []
    previous_cumulative = Decimal("0")
    cutoff_point: BranchGoalPacePoint | None = None
    distribution_points = calendar_aligned_distribution["points"]
    for index, distribution_point in enumerate(distribution_points):
        progress = distribution_point["cumulative_weight"]
        normalized_weight = distribution_point["normalized_daily_weight"]
        if progress is None or normalized_weight is None:
            raise BranchForecastDetailConsistencyError(
                "calendar_aligned_distribution contiene pesos nulos para goal_pace."
            )
        if not progress.is_finite():
            raise BranchForecastDetailConsistencyError(
                "historical_expected contiene avance histórico no finito."
            )
        expected_cumulative = goal_month * progress
        expected_daily = expected_cumulative - previous_cumulative
        if index == len(distribution_points) - 1:
            expected_cumulative = goal_month
            expected_daily = expected_cumulative - previous_cumulative
        if expected_daily < 0:
            raise BranchForecastDetailConsistencyError(
                "historical_expected produce incrementos negativos para goal_pace."
            )
        point: BranchGoalPacePoint = {
            "day": distribution_point["day"],
            "date": distribution_point["date"],
            "historical_progress_pct": progress,
            "goal_expected_daily": expected_daily,
            "goal_expected_cumulative": expected_cumulative,
        }
        points.append(point)
        if point["day"] == cutoff_day:
            cutoff_point = point
        previous_cumulative = expected_cumulative

    if cutoff_point is None:
        raise BranchForecastDetailConsistencyError(
            "historical_expected no contiene el día de corte para goal_pace."
        )
    _require_detail_match(
        actual=cutoff_point["historical_progress_pct"],
        expected=historical_expected["historical_progress_pct_at_cutoff"],
        field_name="goal_pace.cutoff.historical_progress_pct",
    )

    goal_expected_mtd_at_cutoff = cutoff_point[
        "goal_expected_cumulative"
    ]
    gap_vs_goal_pace = real_mtd_at_cutoff - goal_expected_mtd_at_cutoff
    gap_vs_goal_pace_pct = (
        gap_vs_goal_pace / goal_expected_mtd_at_cutoff
        if goal_expected_mtd_at_cutoff > 0
        else None
    )
    result.update(
        {
            "goal_expected_mtd_at_cutoff": goal_expected_mtd_at_cutoff,
            "gap_vs_goal_pace": gap_vs_goal_pace,
            "gap_vs_goal_pace_pct": gap_vs_goal_pace_pct,
            "points": points,
        }
    )

    if projected_close is None:
        result["status"] = "projection_unavailable"
        return result

    projected_path = build_branch_projected_daily_path(
        expected_curve=historical_expected,
        target_month=target_month,
        cutoff_day=cutoff_day,
        metric_basis="total_mtd",
        current_mtd_at_cutoff=real_mtd_at_cutoff,
        projected_close=projected_close,
    )
    result["projected_path"] = projected_path
    if projected_path["status"] != "available":
        result["status"] = "projection_unavailable"
        return result

    _require_detail_match(
        actual=projected_path["points"][0]["projected_cumulative_total"],
        expected=real_mtd_at_cutoff,
        field_name="goal_pace.projected_path.cutoff",
    )
    _require_detail_match(
        actual=projected_path["points"][-1]["projected_cumulative_total"],
        expected=projected_close,
        field_name="goal_pace.projected_path.month_end",
    )
    result.update(
        {
            "status": "available",
            "projected_gap_to_goal": projected_close - goal_month,
            "projected_goal_attainment_pct": projected_close / goal_month,
        }
    )
    return result


def _build_detail_comparison_years(
    *,
    target_month: date,
    history_window: dict[str, Any],
) -> list[int]:
    try:
        history_start = date.fromisoformat(str(history_window["start"]))
        history_end = date.fromisoformat(str(history_window["end_exclusive"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise BranchForecastDetailConsistencyError(
            "El forecast base no contiene una ventana histórica válida."
        ) from exc

    return [
        year
        for year in range(history_start.year, history_end.year + 1)
        if history_start
        <= date(year, target_month.month, 1)
        < history_end
    ]


def _build_current_track_detail(
    *,
    sucursal_canon: str,
    target_month: date,
    track_date: date,
    resolved_cutoff_version_id: int,
    forecast_summary: dict[str, Any],
) -> dict[str, Any]:
    try:
        selections = select_track_daily_branch_versions(
            sucursal_canon=sucursal_canon,
            start_date=target_month,
            cutoff_date=track_date,
            resolved_cutoff_version_id=resolved_cutoff_version_id,
        )
    except ValueError as exc:
        if "versión resuelta del corte" in str(exc):
            raise BranchForecastDetailConsistencyError(str(exc)) from exc
        raise

    points = [
        {
            "day": item["track_date"].day,
            "date": item["track_date"],
            "version_id": item["version_id"],
            "version_type": item["version_type"],
            "selection_reason": item["selection_reason"],
            "base_mtd": item["ingreso_real_base_mtd"],
            "agregadora_mtd": item["ingreso_real_agregadora_mtd"],
            "total_mtd": item["ingreso_real_total_mtd"],
        }
        for item in selections
    ]
    if not points or points[-1]["date"] != track_date:
        raise BranchForecastDetailConsistencyError(
            "La serie Track no contiene el punto correspondiente al día de corte."
        )

    cutoff_point = points[-1]
    if cutoff_point["version_id"] != resolved_cutoff_version_id:
        raise BranchForecastDetailConsistencyError(
            "La serie Track no utilizó la versión resuelta para el día de corte."
        )
    _require_detail_match(
        actual=cutoff_point["base_mtd"],
        expected=forecast_summary.get("real_base_mtd"),
        field_name="current_track.cutoff.base_mtd",
    )
    _require_detail_match(
        actual=cutoff_point["agregadora_mtd"],
        expected=forecast_summary.get("real_agregadora_mtd"),
        field_name="current_track.cutoff.agregadora_mtd",
    )
    _require_detail_match(
        actual=cutoff_point["total_mtd"],
        expected=forecast_summary.get("real_mtd"),
        field_name="current_track.cutoff.total_mtd",
    )

    selected_dates = {point["date"] for point in points}
    expected_dates = [
        target_month + timedelta(days=offset)
        for offset in range((track_date - target_month).days + 1)
    ]
    return {
        "source_basis": "track_daily_mart",
        "points_count": len(points),
        "expected_days_to_cutoff": len(expected_dates),
        "selected_days": [point["day"] for point in points],
        "missing_dates": [
            expected_date
            for expected_date in expected_dates
            if expected_date not in selected_dates
        ],
        "points": points,
    }


def _validate_historical_expected_detail(
    *,
    expected_curve: BranchHistoricalExpectedCurve,
    forecast_summary: dict[str, Any],
) -> None:
    if expected_curve["status"] != "available":
        return
    if not expected_curve["points"]:
        raise BranchForecastDetailConsistencyError(
            "La curva histórica esperada disponible no contiene puntos."
        )
    _require_detail_match(
        actual=expected_curve["historical_progress_pct_at_cutoff"],
        expected=forecast_summary.get("historical_progress_pct"),
        field_name="historical_expected.cutoff.progress_pct",
    )
    _require_detail_match(
        actual=expected_curve["historical_expected_mtd_at_cutoff"],
        expected=forecast_summary.get("historical_expected_mtd"),
        field_name="historical_expected.cutoff.expected_mtd",
    )
    _require_detail_match(
        actual=expected_curve["points"][-1]["expected_cumulative_total"],
        expected=forecast_summary.get("historical_expected_month_total"),
        field_name="historical_expected.month_end.expected_total",
    )


def _build_comparable_base_projection_detail(
    *,
    expected_curve: BranchHistoricalExpectedCurve,
    target_month: date,
    cutoff_day: int,
    forecast_summary: dict[str, Any],
    projection_quality_issue: Any,
) -> dict[str, Any]:
    method = "stable_historical_pace_base"
    formula = "base_projected_close = real_base_mtd / historical_progress_pct"
    confidence = forecast_summary.get("confidence")
    current_base_mtd = _detail_decimal(
        forecast_summary.get("real_base_mtd"),
        field_name="summary.real_base_mtd",
    )
    historical_progress_pct = _detail_decimal(
        forecast_summary.get("historical_progress_pct"),
        field_name="summary.historical_progress_pct",
    )

    empty_result = {
        "method": method,
        "formula": formula,
        "metric_basis": "base_mtd",
        "projected_close": None,
        "confidence": confidence,
        "quality_issue": projection_quality_issue,
        "path": None,
    }
    if projection_quality_issue:
        return {"status": "blocked_by_forecast_quality", **empty_result}
    if current_base_mtd is None:
        return {"status": "missing_base_mtd", **empty_result}
    if historical_progress_pct is None or historical_progress_pct <= 0:
        return {"status": "invalid_historical_progress", **empty_result}

    base_projected_close = current_base_mtd / historical_progress_pct
    path = build_branch_projected_daily_path(
        expected_curve=expected_curve,
        target_month=target_month,
        cutoff_day=cutoff_day,
        metric_basis="base_mtd",
        current_mtd_at_cutoff=current_base_mtd,
        projected_close=base_projected_close,
    )
    status = (
        "available"
        if path["status"] == "available"
        else "projected_path_unavailable"
    )
    return {
        "status": status,
        "method": method,
        "formula": formula,
        "metric_basis": "base_mtd",
        "projected_close": base_projected_close,
        "confidence": confidence,
        "quality_issue": projection_quality_issue,
        "path": path,
    }


def build_branch_forecast_detail(
    *,
    sucursal_canon: str,
    track_date: date,
    generation_mode: str,
    track_daily_version_id: int,
) -> dict[str, Any]:
    normalized_branch = str(sucursal_canon or "").strip().upper()
    if not normalized_branch:
        raise ValueError("sucursal_canon es requerido.")
    if normalized_branch in EXCLUDED_BRANCHES:
        raise ValueError("La sucursal solicitada está excluida de Track.")

    forecast = build_venta_total_forecast(
        track_date=track_date,
        generation_mode=generation_mode,
        track_daily_version_id=track_daily_version_id,
        scope="branch",
        branch=normalized_branch,
    )
    forecast_metadata = forecast["metadata"]
    forecast_summary = forecast["summary"]
    resolved_cutoff_version_id = int(
        forecast_metadata["track_daily_version_id"]
    )
    target_month = date.fromisoformat(forecast_metadata["target_month"])
    cutoff_day = track_date.day
    comparison_years = _build_detail_comparison_years(
        target_month=target_month,
        history_window=forecast_metadata["history_window"],
    )

    current_track = _build_current_track_detail(
        sucursal_canon=normalized_branch,
        target_month=target_month,
        track_date=track_date,
        resolved_cutoff_version_id=resolved_cutoff_version_id,
        forecast_summary=forecast_summary,
    )
    historical_series = build_branch_historical_daily_series(
        sucursal_canon=normalized_branch,
        target_month=target_month,
        comparison_years=comparison_years,
        cutoff_day=cutoff_day,
    )
    historical_expected_month_total = _detail_decimal(
        forecast_summary.get("historical_expected_month_total"),
        field_name="summary.historical_expected_month_total",
    )
    historical_progress_pct_at_cutoff = _detail_decimal(
        forecast_summary.get("historical_progress_pct"),
        field_name="summary.historical_progress_pct",
    )
    calendar_aligned_distribution = build_branch_calendar_aligned_daily_weights(
        historical_series=historical_series,
        target_month=target_month,
        cutoff_day=cutoff_day,
        historical_progress_pct_at_cutoff=historical_progress_pct_at_cutoff,
    )
    historical_expected = (
        _build_branch_calendar_aligned_historical_expected_daily_curve(
            distribution=calendar_aligned_distribution,
            target_month=target_month,
            cutoff_day=cutoff_day,
            historical_expected_month_total=historical_expected_month_total,
        )
    )
    _validate_historical_expected_detail(
        expected_curve=historical_expected,
        forecast_summary=forecast_summary,
    )

    forecast_data_quality = forecast["data_quality"]
    projection_quality_issue = forecast_data_quality.get(
        "branch_projection_quality_issue"
    )
    comparable_base_projection = _build_comparable_base_projection_detail(
        expected_curve=historical_expected,
        target_month=target_month,
        cutoff_day=cutoff_day,
        forecast_summary=forecast_summary,
        projection_quality_issue=projection_quality_issue,
    )

    summary = dict(forecast_summary)
    summary["total_projection_basis"] = {
        "metric_basis": "total_mtd",
        "includes_agregadoras": True,
        "source": "existing_stable_forecast",
    }
    goal_pace = _build_branch_goal_pace_detail(
        goal_status=str(forecast_data_quality.get("goal_status") or ""),
        goal_month=_detail_decimal(
            forecast_summary.get("goal_month"),
            field_name="summary.goal_month",
        ),
        real_mtd_at_cutoff=_detail_decimal(
            forecast_summary.get("real_mtd"),
            field_name="summary.real_mtd",
        ),
        projected_close=_detail_decimal(
            forecast_summary.get("projected_close"),
            field_name="summary.projected_close",
        ),
        target_month=target_month,
        cutoff_day=cutoff_day,
        historical_expected=historical_expected,
        calendar_aligned_distribution=calendar_aligned_distribution,
    )
    for summary_field, goal_pace_field in (
        ("weighted_goal_mtd", "goal_expected_mtd_at_cutoff"),
        ("gap_vs_weighted_goal", "gap_vs_goal_pace"),
        ("gap_vs_weighted_goal_pct", "gap_vs_goal_pace_pct"),
    ):
        if forecast_summary.get(summary_field) is not None:
            _require_detail_match(
                actual=goal_pace[goal_pace_field],
                expected=forecast_summary[summary_field],
                field_name=f"goal_pace.{goal_pace_field}",
            )
    return {
        "status": "ok",
        "metadata": {
            "sucursal_canon": normalized_branch,
            "track_date": track_date,
            "target_month": target_month,
            "cutoff_day": cutoff_day,
            "generation_mode": generation_mode,
            "resolved_version": {"id": resolved_cutoff_version_id},
            "history_window": dict(forecast_metadata["history_window"]),
            "comparison_years": comparison_years,
        },
        "summary": summary,
        "calendar_aligned_distribution": calendar_aligned_distribution,
        "goal_pace": goal_pace,
        "forecast_context": {
            "forecast_cutoff": forecast["forecast_cutoff"],
            "same_day_history": forecast["same_day_history"],
        },
        "series": {
            "current_track": current_track,
            "historical_years": {
                "source_basis": "venta_total_base",
                "items": historical_series,
            },
            "historical_expected": {
                "source_basis": "venta_total_base",
                **historical_expected,
            },
            "comparable_base_projection": comparable_base_projection,
        },
        "data_quality": {
            "forecast": forecast_data_quality,
            "current_series": {
                "points_count": current_track["points_count"],
                "expected_days_to_cutoff": current_track[
                    "expected_days_to_cutoff"
                ],
                "missing_dates": current_track["missing_dates"],
            },
            "source_comparability": {
                "historical_basis": "venta_total_base",
                "current_comparable_basis": "base_mtd",
                "executive_total_basis": "total_mtd",
                "agregadoras_not_present_in_historical_series": True,
            },
            "warnings": list(forecast["warnings"]),
        },
    }
