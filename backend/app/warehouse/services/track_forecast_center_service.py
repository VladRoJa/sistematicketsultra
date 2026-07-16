from __future__ import annotations

from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Literal, Sequence

from sqlalchemy import and_, bindparam, or_, text

from app.extensions import db
from app.models.sucursal_model import Sucursal, SucursalOperationalStatus
from app.models.suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
)
from app.models.warehouse import (
    TrackBranchCatalogORM,
    TrackDailyMartORM,
    TrackDailyVersionORM,
    TrackMonthlyTargetORM,
    VentaTotalSnapshotORM,
)
from app.warehouse.services.track_branch_cohort_service import (
    TRACK_BRANCH_COHORT_LEGACY_21,
    TRACK_BRANCH_COHORT_NEW_GYMS,
    TRACK_BRANCH_COHORT_TOTAL_ULTRA,
    get_track_branch_cohort_definitions,
    resolve_track_branch_cohort_from_display_order,
)
from app.warehouse.services.track_forecast_service import (
    EXCLUDED_BRANCHES,
    _build_available_branch_historical_year_series,
    _build_branch_calendar_aligned_historical_expected_daily_curve,
    _build_branch_goal_pace_detail,
    _build_empty_branch_historical_year_series,
    _build_history_window,
    _resolve_branch_projection_quality_issue,
    _select_track_daily_branch_version_candidates,
    build_branch_calendar_aligned_daily_weights,
    build_branch_current_track_daily_values,
)


GLOBAL_CENTER_ROLES = frozenset(
    {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "LECTOR_GLOBAL"}
)
CENTER_SCOPES = frozenset({"national", "region", "authorized_pool", "branch"})
CENTER_COHORTS = frozenset(
    {
        "all",
        TRACK_BRANCH_COHORT_TOTAL_ULTRA,
        TRACK_BRANCH_COHORT_LEGACY_21,
        TRACK_BRANCH_COHORT_NEW_GYMS,
    }
)
CENTER_BREAKDOWNS = frozenset({"cohort", "region", "branch", "none"})
PUBLIC_COHORT_LABELS = {
    TRACK_BRANCH_COHORT_TOTAL_ULTRA: "Total Ultra",
    TRACK_BRANCH_COHORT_LEGACY_21: "21 Gyms",
    TRACK_BRANCH_COHORT_NEW_GYMS: "Nuevos",
}

MetricStatus = Literal["available", "partial", "unavailable"]


class ForecastCenterError(RuntimeError):
    pass


class ForecastCenterValidationError(ForecastCenterError):
    pass


class ForecastCenterAuthorizationError(ForecastCenterError):
    pass


class ForecastCenterNotFoundError(ForecastCenterError):
    pass


@dataclass(frozen=True)
class ForecastCenterAccess:
    type: Literal["global", "primary_branch", "assigned_branches"]
    is_global: bool
    authorized_branch_ids: tuple[int, ...]
    authorized_branch_count: int
    fallback_used: bool = False
    fallback_reason: str | None = None
    role: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "is_global": self.is_global,
            "authorized_branch_ids": list(self.authorized_branch_ids),
            "authorized_branch_count": self.authorized_branch_count,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class ForecastCenterExclusion:
    sucursal_canon: str | None
    reasons: tuple[str, ...]
    stage: str
    affects_metrics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForecastCenterBranch:
    sucursal_canon: str
    sucursal_id: int
    label: str
    display_order: int
    operational_status: str
    cohort: str
    region_key: str | None
    region_label: str | None
    region_assignment_status: Literal["available", "missing", "overlapping"]


@dataclass
class ForecastCenterUniverse:
    branches: list[ForecastCenterBranch]
    exclusions: list[ForecastCenterExclusion]
    unauthorized_removed: int
    total_region_branch_counts: dict[str, int]


@dataclass
class ForecastCenterBulkBundle:
    target_month: date
    cutoff_day: int
    branches: list[ForecastCenterBranch]
    mart_by_branch: dict[str, TrackDailyMartORM]
    target_by_branch: dict[str, TrackMonthlyTargetORM]
    current_candidates_by_branch: dict[str, list[dict[str, Any]]]
    historical_series_by_branch: dict[str, list[dict[str, Any]]]
    canonical_snapshot_id: int | None
    canonical_business_date: date | None
    loader_invocations: dict[str, int]


@dataclass
class BranchForecastCenterResult:
    identity: dict[str, Any]
    summary: dict[str, Decimal | int | None]
    series: dict[str, list[dict[str, Any]]]
    quality: dict[str, Any]
    drilldown: dict[str, Any]


def _normalize_role(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_branch(value: Any) -> str:
    return str(value or "").strip().upper()


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _first_day_of_month(value: date) -> date:
    return value.replace(day=1)


def _metric_status(*, eligible: int, included: int) -> MetricStatus:
    if included <= 0:
        return "unavailable"
    if included >= eligible:
        return "available"
    return "partial"


def _metric_coverage(*, eligible: int, included: int) -> dict[str, Any]:
    return {
        "status": _metric_status(eligible=eligible, included=included),
        "eligible_branch_count": eligible,
        "included_branch_count": included,
        "excluded_branch_count": max(eligible - included, 0),
    }


def resolve_forecast_center_access(user: Any) -> ForecastCenterAccess:
    if user is None:
        raise ForecastCenterAuthorizationError("Usuario no encontrado.")

    role = _normalize_role(getattr(user, "rol", None))
    primary_branch_id = getattr(user, "sucursal_id", None)
    try:
        primary_branch_id = int(primary_branch_id)
    except (TypeError, ValueError):
        primary_branch_id = None

    if role in GLOBAL_CENTER_ROLES:
        return ForecastCenterAccess(
            type="global",
            is_global=True,
            authorized_branch_ids=(),
            authorized_branch_count=0,
            role=role,
        )

    if role == "GERENTE":
        if primary_branch_id is None:
            raise ForecastCenterAuthorizationError(
                "El gerente no tiene una sucursal primaria válida."
            )
        return ForecastCenterAccess(
            type="primary_branch",
            is_global=False,
            authorized_branch_ids=(primary_branch_id,),
            authorized_branch_count=1,
            role=role,
        )

    if role == "GERENTE_REGIONAL":
        assigned_ids: set[int] = set()
        for value in getattr(user, "sucursales_ids", None) or []:
            try:
                assigned_ids.add(int(value))
            except (TypeError, ValueError):
                continue
        if assigned_ids:
            normalized = tuple(sorted(assigned_ids))
            return ForecastCenterAccess(
                type="assigned_branches",
                is_global=False,
                authorized_branch_ids=normalized,
                authorized_branch_count=len(normalized),
                role=role,
            )
        if primary_branch_id is None:
            raise ForecastCenterAuthorizationError(
                "El gerente regional no tiene sucursales autorizadas."
            )
        return ForecastCenterAccess(
            type="primary_branch",
            is_global=False,
            authorized_branch_ids=(primary_branch_id,),
            authorized_branch_count=1,
            fallback_used=True,
            fallback_reason="empty_assigned_branches_used_primary_branch",
            role=role,
        )

    raise ForecastCenterAuthorizationError(
        "No autorizado para consultar el Centro de Forecast."
    )


def _load_region_assignments(
    *,
    branch_ids: Sequence[int],
    requested_track_date: date,
) -> dict[int, list[tuple[SuiteSucursalRegionAssignmentORM, SuiteRegionORM]]]:
    if not branch_ids:
        return {}
    rows = (
        db.session.query(SuiteSucursalRegionAssignmentORM, SuiteRegionORM)
        .join(
            SuiteRegionORM,
            SuiteRegionORM.id == SuiteSucursalRegionAssignmentORM.region_id,
        )
        .filter(
            SuiteSucursalRegionAssignmentORM.sucursal_id.in_(tuple(branch_ids)),
            SuiteSucursalRegionAssignmentORM.valid_from <= requested_track_date,
            or_(
                SuiteSucursalRegionAssignmentORM.valid_to.is_(None),
                SuiteSucursalRegionAssignmentORM.valid_to >= requested_track_date,
            ),
            SuiteRegionORM.is_active.is_(True),
        )
        .all()
    )
    result: dict[int, list[tuple[Any, Any]]] = defaultdict(list)
    for assignment, region in rows:
        result[int(assignment.sucursal_id)].append((assignment, region))
    return dict(result)


def resolve_forecast_center_universe(
    *,
    access: ForecastCenterAccess,
    requested_track_date: date,
) -> ForecastCenterUniverse:
    catalog_rows = (
        db.session.query(TrackBranchCatalogORM, Sucursal)
        .outerjoin(Sucursal, Sucursal.sucursal_id == TrackBranchCatalogORM.sucursal_id)
        .order_by(
            TrackBranchCatalogORM.display_order.asc(),
            TrackBranchCatalogORM.sucursal_canon.asc(),
        )
        .all()
    )
    branch_ids = sorted(
        {
            int(catalog.sucursal_id)
            for catalog, _ in catalog_rows
            if catalog.sucursal_id is not None
        }
    )
    regions_by_branch_id = _load_region_assignments(
        branch_ids=branch_ids,
        requested_track_date=requested_track_date,
    )

    authorized_ids = set(access.authorized_branch_ids)
    branches: list[ForecastCenterBranch] = []
    exclusions: list[ForecastCenterExclusion] = []
    unauthorized_removed = 0
    total_region_branch_counts: Counter[str] = Counter()

    for catalog, sucursal in catalog_rows:
        canon = _normalize_branch(catalog.sucursal_canon)
        reasons: list[str] = []
        if not bool(catalog.is_track_active):
            reasons.append("inactive_track_branch")
        if catalog.sucursal_id is None or sucursal is None:
            reasons.append("missing_sucursal_id")
        if canon in EXCLUDED_BRANCHES:
            reasons.append("forecast_excluded_branch")
        if (
            sucursal is not None
            and sucursal.operational_status != SucursalOperationalStatus.ACTIVA
        ):
            reasons.append("non_active_operational_status")

        cohort = resolve_track_branch_cohort_from_display_order(
            catalog.display_order
        )
        if cohort is None:
            reasons.append("unknown_cohort")

        if reasons:
            exclusions.append(
                ForecastCenterExclusion(
                    sucursal_canon=canon,
                    reasons=tuple(dict.fromkeys(reasons)),
                    stage="operational_universe",
                    affects_metrics=("all",),
                )
            )
            continue

        branch_id = int(catalog.sucursal_id)
        assignments = regions_by_branch_id.get(branch_id, [])
        region_key: str | None = None
        region_label: str | None = None
        region_status: Literal["available", "missing", "overlapping"]
        if len(assignments) == 1:
            region = assignments[0][1]
            region_key = str(region.region_key)
            region_label = str(region.region_label)
            region_status = "available"
            total_region_branch_counts[region_key] += 1
        elif not assignments:
            region_status = "missing"
            exclusions.append(
                ForecastCenterExclusion(
                    sucursal_canon=canon,
                    reasons=("missing_region_assignment",),
                    stage="region_resolution",
                    affects_metrics=("region_breakdown",),
                )
            )
        else:
            region_status = "overlapping"
            exclusions.append(
                ForecastCenterExclusion(
                    sucursal_canon=canon,
                    reasons=("overlapping_region_assignments",),
                    stage="region_resolution",
                    affects_metrics=("region_breakdown",),
                )
            )

        if not access.is_global and branch_id not in authorized_ids:
            unauthorized_removed += 1
            exclusions.append(
                ForecastCenterExclusion(
                    sucursal_canon=None,
                    reasons=("unauthorized_branch",),
                    stage="authorization",
                    affects_metrics=("all",),
                )
            )
            continue

        branches.append(
            ForecastCenterBranch(
                sucursal_canon=canon,
                sucursal_id=branch_id,
                label=str(catalog.track_label or sucursal.sucursal or canon),
                display_order=int(catalog.display_order),
                operational_status=str(sucursal.operational_status),
                cohort=str(cohort),
                region_key=region_key,
                region_label=region_label,
                region_assignment_status=region_status,
            )
        )

    return ForecastCenterUniverse(
        branches=branches,
        exclusions=exclusions,
        unauthorized_removed=unauthorized_removed,
        total_region_branch_counts=dict(total_region_branch_counts),
    )


def _validate_scope_for_access(
    *,
    access: ForecastCenterAccess,
    scope: str,
) -> None:
    if scope not in CENTER_SCOPES:
        raise ForecastCenterValidationError("scope inválido.")
    if access.role == "GERENTE" and scope != "branch":
        raise ForecastCenterAuthorizationError(
            "El gerente sólo puede consultar su sucursal."
        )
    if access.role == "GERENTE_REGIONAL" and scope == "national":
        raise ForecastCenterAuthorizationError(
            "El gerente regional no puede consultar el alcance nacional."
        )
    if access.is_global and scope == "authorized_pool":
        raise ForecastCenterValidationError(
            "authorized_pool sólo aplica a gerente regional."
        )


def select_forecast_center_scope(
    *,
    universe: ForecastCenterUniverse,
    access: ForecastCenterAccess,
    scope: str,
    scope_id: str | None,
    cohort: str,
) -> list[ForecastCenterBranch]:
    _validate_scope_for_access(access=access, scope=scope)
    if cohort not in CENTER_COHORTS:
        raise ForecastCenterValidationError("cohort inválida.")

    normalized_scope_id = _normalize_branch(scope_id)
    branches = list(universe.branches)

    if scope in {"national", "authorized_pool"}:
        if normalized_scope_id:
            raise ForecastCenterValidationError(
                "scope_id debe omitirse para el alcance solicitado."
            )
    elif scope == "region":
        if not normalized_scope_id:
            raise ForecastCenterValidationError("scope_id es requerido para region.")
        known_region = any(
            branch.region_key == normalized_scope_id for branch in universe.branches
        )
        if not known_region:
            if access.is_global:
                raise ForecastCenterNotFoundError("Región no encontrada.")
            raise ForecastCenterAuthorizationError("Región fuera del alcance autorizado.")
        branches = [
            branch for branch in branches if branch.region_key == normalized_scope_id
        ]
    elif scope == "branch":
        if not normalized_scope_id:
            if len(branches) == 1:
                normalized_scope_id = branches[0].sucursal_canon
            else:
                raise ForecastCenterValidationError(
                    "scope_id es requerido para branch."
                )
        known_anywhere = (
            db.session.query(TrackBranchCatalogORM.sucursal_canon)
            .filter(
                TrackBranchCatalogORM.sucursal_canon == normalized_scope_id
            )
            .first()
            is not None
        )
        selected = [
            branch
            for branch in branches
            if branch.sucursal_canon == normalized_scope_id
        ]
        if not selected:
            if known_anywhere and not access.is_global:
                raise ForecastCenterAuthorizationError(
                    "Sucursal fuera del alcance autorizado."
                )
            raise ForecastCenterNotFoundError("Sucursal no encontrada.")
        branches = selected

    if cohort not in {"all", TRACK_BRANCH_COHORT_TOTAL_ULTRA}:
        branches = [branch for branch in branches if branch.cohort == cohort]

    return branches


def _load_current_candidates_bulk(
    *,
    branch_canons: Sequence[str],
    target_month: date,
    track_date: date,
    track_daily_version_id: int,
) -> dict[str, list[dict[str, Any]]]:
    if not branch_canons:
        return {}
    rows = (
        db.session.query(TrackDailyVersionORM, TrackDailyMartORM)
        .join(
            TrackDailyMartORM,
            TrackDailyMartORM.track_daily_version_id == TrackDailyVersionORM.id,
        )
        .filter(
            TrackDailyMartORM.sucursal_canon.in_(tuple(branch_canons)),
            TrackDailyVersionORM.track_date.between(target_month, track_date),
            TrackDailyMartORM.track_date == TrackDailyVersionORM.track_date,
            or_(
                and_(
                    TrackDailyVersionORM.track_date == track_date,
                    TrackDailyVersionORM.id == track_daily_version_id,
                ),
                and_(
                    TrackDailyVersionORM.track_date < track_date,
                    TrackDailyVersionORM.status == "success",
                    TrackDailyVersionORM.is_current.is_(True),
                    TrackDailyVersionORM.version_type.in_(
                        (
                            "cierre_canonico",
                            "base_nocturna_canonica",
                            "preview_operativo",
                        )
                    ),
                ),
            ),
        )
        .order_by(
            TrackDailyMartORM.sucursal_canon.asc(),
            TrackDailyVersionORM.track_date.asc(),
            TrackDailyVersionORM.id.desc(),
        )
        .all()
    )
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for version, mart in rows:
        result[_normalize_branch(mart.sucursal_canon)].append(
            {
                "track_date": version.track_date,
                "version_id": int(version.id),
                "version_type": str(version.version_type),
                "ingreso_real_base_mtd": mart.ingreso_real_base_mtd,
                "ingreso_real_agregadora_mtd": mart.ingreso_real_agregadora_mtd,
                "ingreso_real_total_mtd": mart.ingreso_real_total_mtd,
            }
        )
    return dict(result)


def _load_historical_series_bulk(
    *,
    branch_canons: Sequence[str],
    target_month: date,
    cutoff_day: int,
) -> dict[str, list[dict[str, Any]]]:
    comparison_years = [target_month.year - offset for offset in (3, 2, 1)]
    business_months = [date(year, target_month.month, 1) for year in comparison_years]
    history_start, history_end = _build_history_window(target_month)
    snapshots = (
        db.session.query(VentaTotalSnapshotORM)
        .filter(
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
            VentaTotalSnapshotORM.business_date >= history_start,
            VentaTotalSnapshotORM.business_date < history_end,
        )
        .all()
    )
    selected_by_year: dict[int, VentaTotalSnapshotORM] = {}
    for snapshot in snapshots:
        if snapshot.business_date.month != target_month.month:
            continue
        current = selected_by_year.get(snapshot.business_date.year)
        if current is None or (
            snapshot.business_date,
            snapshot.captured_at,
            snapshot.id,
        ) > (current.business_date, current.captured_at, current.id):
            selected_by_year[snapshot.business_date.year] = snapshot

    snapshot_ids = tuple(snapshot.id for snapshot in selected_by_year.values())
    totals: dict[tuple[int, str], dict[date, Decimal]] = defaultdict(dict)
    if snapshot_ids and branch_canons:
        rows = db.session.execute(
            text(
                """
                SELECT snapshot_id, upper(trim(sucursal_canon)) AS sucursal_canon,
                       sale_date, SUM(total)::numeric AS total
                FROM track_venta_total_daily_branch_agg
                WHERE snapshot_id IN :snapshot_ids
                  AND upper(trim(sucursal_canon)) IN :branch_canons
                GROUP BY snapshot_id, upper(trim(sucursal_canon)), sale_date
                ORDER BY snapshot_id, sucursal_canon, sale_date
                """
            ).bindparams(
                bindparam("snapshot_ids", expanding=True),
                bindparam("branch_canons", expanding=True),
            ),
            {
                "snapshot_ids": snapshot_ids,
                "branch_canons": tuple(branch_canons),
            },
        ).mappings().all()
        for row in rows:
            totals[(int(row["snapshot_id"]), str(row["sucursal_canon"]))][
                row["sale_date"]
            ] = _decimal(row["total"]) or Decimal("0")

    result: dict[str, list[dict[str, Any]]] = {}
    for canon in branch_canons:
        items: list[dict[str, Any]] = []
        for year, business_month in zip(comparison_years, business_months):
            snapshot = selected_by_year.get(year)
            if snapshot is None:
                items.append(
                    _build_empty_branch_historical_year_series(
                        year=year,
                        business_month=business_month,
                        status="no_canonical_snapshot",
                        snapshot=None,
                    )
                )
                continue
            daily_totals = totals.get((int(snapshot.id), canon), {})
            if not daily_totals:
                items.append(
                    _build_empty_branch_historical_year_series(
                        year=year,
                        business_month=business_month,
                        status="no_branch_rows",
                        snapshot=snapshot,
                    )
                )
                continue
            items.append(
                _build_available_branch_historical_year_series(
                    year=year,
                    business_month=business_month,
                    snapshot=snapshot,
                    daily_totals=daily_totals,
                    cutoff_day=cutoff_day,
                )
            )
        result[canon] = items

    return result


def _load_canonical_cutoff_bulk(
    *,
    target_month: date,
    track_date: date,
) -> tuple[int | None, date | None]:
    next_month = (
        date(target_month.year + 1, 1, 1)
        if target_month.month == 12
        else date(target_month.year, target_month.month + 1, 1)
    )
    snapshot = (
        VentaTotalSnapshotORM.query.filter(
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
            VentaTotalSnapshotORM.business_date >= target_month,
            VentaTotalSnapshotORM.business_date < next_month,
            VentaTotalSnapshotORM.business_date <= track_date,
        )
        .order_by(
            VentaTotalSnapshotORM.business_date.desc(),
            VentaTotalSnapshotORM.captured_at.desc(),
            VentaTotalSnapshotORM.id.desc(),
        )
        .first()
    )
    if snapshot is None:
        return None, None
    return int(snapshot.id), snapshot.business_date


def bulk_load_forecast_center_data(
    *,
    branches: Sequence[ForecastCenterBranch],
    track_date: date,
    track_daily_version_id: int,
) -> ForecastCenterBulkBundle:
    branch_canons = tuple(branch.sucursal_canon for branch in branches)
    target_month = _first_day_of_month(track_date)
    cutoff_day = track_date.day
    loader_invocations: Counter[str] = Counter()

    loader_invocations["mart"] += 1
    mart_rows = (
        TrackDailyMartORM.query.filter(
            TrackDailyMartORM.track_daily_version_id == track_daily_version_id,
            TrackDailyMartORM.sucursal_canon.in_(branch_canons),
        ).all()
        if branch_canons
        else []
    )
    mart_by_branch = {
        _normalize_branch(row.sucursal_canon): row for row in mart_rows
    }

    loader_invocations["targets"] += 1
    target_rows = (
        TrackMonthlyTargetORM.query.filter(
            TrackMonthlyTargetORM.target_month == target_month,
            TrackMonthlyTargetORM.is_active.is_(True),
            TrackMonthlyTargetORM.sucursal_canon.in_(branch_canons),
        ).all()
        if branch_canons
        else []
    )
    target_by_branch = {
        _normalize_branch(row.sucursal_canon): row for row in target_rows
    }

    loader_invocations["current_daily_versions"] += 1
    current_candidates = _load_current_candidates_bulk(
        branch_canons=branch_canons,
        target_month=target_month,
        track_date=track_date,
        track_daily_version_id=track_daily_version_id,
    )

    loader_invocations["historical_snapshots_and_daily_totals"] += 1
    historical = _load_historical_series_bulk(
        branch_canons=branch_canons,
        target_month=target_month,
        cutoff_day=cutoff_day,
    )

    loader_invocations["canonical_cutoff"] += 1
    snapshot_id, snapshot_date = _load_canonical_cutoff_bulk(
        target_month=target_month,
        track_date=track_date,
    )

    return ForecastCenterBulkBundle(
        target_month=target_month,
        cutoff_day=cutoff_day,
        branches=list(branches),
        mart_by_branch=mart_by_branch,
        target_by_branch=target_by_branch,
        current_candidates_by_branch=current_candidates,
        historical_series_by_branch=historical,
        canonical_snapshot_id=snapshot_id,
        canonical_business_date=snapshot_date,
        loader_invocations=dict(loader_invocations),
    )


def _build_current_series(
    *,
    candidates: list[dict[str, Any]],
    target_month: date,
    track_date: date,
    track_daily_version_id: int,
) -> tuple[list[dict[str, Any]], list[date]]:
    selected = _select_track_daily_branch_version_candidates(
        candidates=candidates,
        cutoff_date=track_date,
        resolved_cutoff_version_id=track_daily_version_id,
    )
    cumulative = [
        {
            "day": candidate["track_date"].day,
            "date": candidate["track_date"],
            "version_id": candidate["version_id"],
            "version_type": candidate["version_type"],
            "selection_reason": reason,
            "base_mtd": candidate["ingreso_real_base_mtd"],
            "agregadora_mtd": candidate["ingreso_real_agregadora_mtd"],
            "total_mtd": candidate["ingreso_real_total_mtd"],
        }
        for candidate, reason in selected
    ]
    points = build_branch_current_track_daily_values(cumulative)
    selected_dates = {point["date"] for point in points}
    expected_dates = [
        target_month + timedelta(days=offset)
        for offset in range((track_date - target_month).days + 1)
    ]
    missing_dates = [value for value in expected_dates if value not in selected_dates]
    return points, missing_dates


def calculate_compact_branch_forecast(
    *,
    branch: ForecastCenterBranch,
    bundle: ForecastCenterBulkBundle,
    track_date: date,
    track_daily_version_id: int,
) -> BranchForecastCenterResult | None:
    canon = branch.sucursal_canon
    mart = bundle.mart_by_branch.get(canon)
    if mart is None:
        return None

    real_mtd = _decimal(mart.ingreso_real_total_mtd)
    if real_mtd is None:
        real_mtd = _decimal(mart.ingreso_real_mtd)
    goal_month = _decimal(mart.meta_faycgo_mes)
    if goal_month is None:
        target = bundle.target_by_branch.get(canon)
        goal_month = _decimal(target.meta_faycgo_mes) if target is not None else None
    goal_status = "available" if goal_month is not None and goal_month > 0 else "pending"
    if goal_month is not None and goal_month <= 0:
        goal_status = "invalid"

    historical_series = bundle.historical_series_by_branch.get(canon, [])
    available_history = [
        item for item in historical_series if item["status"] == "available"
    ]
    historical_month_total = sum(
        (item["full_month_total"] for item in available_history), Decimal("0")
    )
    historical_mtd_total = sum(
        (item["mtd_at_cutoff"] for item in available_history), Decimal("0")
    )
    historical_progress = (
        historical_mtd_total / historical_month_total
        if historical_month_total > 0
        else None
    )
    historical_expected_month_total = (
        historical_month_total / Decimal(len(available_history))
        if available_history
        else None
    )
    historical_expected_mtd = (
        historical_mtd_total / Decimal(len(available_history))
        if available_history
        else None
    )
    trend_factor = (
        real_mtd / historical_expected_mtd
        if real_mtd is not None
        and historical_expected_mtd is not None
        and historical_expected_mtd > 0
        else None
    )
    curve = {
        "historical_months": len(available_history),
        "historical_mtd_total": historical_mtd_total,
        "historical_month_total": historical_month_total,
        "historical_progress_pct": historical_progress,
        "confidence": (
            "alta"
            if len(available_history) >= 3
            else "media"
            if len(available_history) == 2
            else "baja"
            if len(available_history) == 1
            else "sin_historia"
        ),
    }
    projected_close = (
        real_mtd / historical_progress
        if real_mtd is not None and historical_progress is not None and historical_progress > 0
        else None
    )
    quality_issue = _resolve_branch_projection_quality_issue(
        scope="branch",
        curve=curve,
        trend_factor=trend_factor,
    )
    if quality_issue:
        projected_close = None

    distribution = build_branch_calendar_aligned_daily_weights(
        historical_series=historical_series,
        target_month=bundle.target_month,
        cutoff_day=bundle.cutoff_day,
        historical_progress_pct_at_cutoff=historical_progress,
    )
    historical_expected = _build_branch_calendar_aligned_historical_expected_daily_curve(
        distribution=distribution,
        target_month=bundle.target_month,
        cutoff_day=bundle.cutoff_day,
        historical_expected_month_total=historical_expected_month_total,
    )
    goal_pace = _build_branch_goal_pace_detail(
        goal_status=goal_status,
        goal_month=goal_month,
        real_mtd_at_cutoff=real_mtd,
        projected_close=projected_close,
        target_month=bundle.target_month,
        cutoff_day=bundle.cutoff_day,
        historical_expected=historical_expected,
        calendar_aligned_distribution=distribution,
    )
    current_points, missing_dates = _build_current_series(
        candidates=bundle.current_candidates_by_branch.get(canon, []),
        target_month=bundle.target_month,
        track_date=track_date,
        track_daily_version_id=track_daily_version_id,
    )

    actual = [
        {
            "date": point["date"],
            "day": point["day"],
            "daily": point["total_daily"],
            "cumulative": point["total_mtd"],
            "status": point["daily_value_status"],
        }
        for point in current_points
    ]
    required = [
        {
            "date": point["date"],
            "day": point["day"],
            "daily": point["goal_expected_daily"],
            "cumulative": point["goal_expected_cumulative"],
            "status": "available",
        }
        for point in goal_pace["points"]
    ]
    projected_path = goal_pace.get("projected_path")
    projected = []
    if projected_path and projected_path.get("status") == "available":
        projected = [
            {
                "date": point["date"],
                "day": point["day"],
                "daily": (
                    None
                    if point["point_kind"] == "cutoff_anchor"
                    else point["projected_daily_increment"]
                ),
                "cumulative": point["projected_cumulative_total"],
                "status": (
                    "cutoff_anchor"
                    if point["point_kind"] == "cutoff_anchor"
                    else "available"
                ),
            }
            for point in projected_path["points"]
        ]

    valid_goal = goal_month is not None and goal_month > 0
    comparable_real = real_mtd if valid_goal else None
    comparable_projection = projected_close if valid_goal else None
    exclusion_reasons: list[str] = []
    if missing_dates:
        exclusion_reasons.append("daily_gaps")
    if branch.region_assignment_status == "missing":
        exclusion_reasons.append("missing_region_assignment")
    elif branch.region_assignment_status == "overlapping":
        exclusion_reasons.append("overlapping_region_assignments")

    return BranchForecastCenterResult(
        identity={
            "sucursal_canon": canon,
            "sucursal_id": branch.sucursal_id,
            "label": branch.label,
            "cohort": branch.cohort,
            "region_key": branch.region_key,
        },
        summary={
            "goal_month": goal_month if valid_goal else None,
            "real_mtd": real_mtd,
            "real_mtd_comparable_to_goal": comparable_real,
            "goal_expected_mtd_at_cutoff": goal_pace["goal_expected_mtd_at_cutoff"],
            "gap_vs_goal_pace": goal_pace["gap_vs_goal_pace"],
            "projected_close": projected_close,
            "projected_close_comparable_to_goal": comparable_projection,
            "projected_gap_to_goal": goal_pace["projected_gap_to_goal"],
            "projected_goal_attainment_pct": goal_pace[
                "projected_goal_attainment_pct"
            ],
            "remaining_to_goal": goal_pace["remaining_to_goal"],
            "remaining_days": goal_pace["remaining_days"],
            "required_daily_average": goal_pace["required_daily_average"],
        },
        series={"actual": actual, "required": required, "projected": projected},
        quality={
            "goal_status": goal_pace["status"],
            "history_status": historical_expected["status"],
            "projection_status": (
                projected_path["status"] if projected_path else "unavailable"
            ),
            "calendar_status": distribution["status"],
            "has_daily_gaps": bool(missing_dates),
            "has_calendar_fallback": bool(distribution["fallback_matches_count"]),
            "exclusion_reasons": exclusion_reasons,
        },
        drilldown={
            "scope": "branch",
            "scope_id": canon,
            "analytic_route": f"/warehouse/track/forecast/branches/{canon}",
        },
    )


def _sum_values(values: Iterable[Decimal | None]) -> tuple[Decimal | None, int]:
    available = [value for value in values if value is not None]
    if not available:
        return None, 0
    return sum(available, Decimal("0")), len(available)


def aggregate_forecast_center_results(
    results: Sequence[BranchForecastCenterResult],
    *,
    eligible_branch_count: int | None = None,
    common_remaining_days: int | None = None,
) -> dict[str, Any]:
    eligible = eligible_branch_count if eligible_branch_count is not None else len(results)
    summaries = [item.summary for item in results]
    goal_month, goal_count = _sum_values(item["goal_month"] for item in summaries)
    real_mtd, real_count = _sum_values(item["real_mtd"] for item in summaries)
    real_comparable, real_comparable_count = _sum_values(
        item["real_mtd_comparable_to_goal"] for item in summaries
    )
    expected, expected_count = _sum_values(
        item["goal_expected_mtd_at_cutoff"] for item in summaries
    )
    projected, projected_count = _sum_values(
        item["projected_close"] for item in summaries
    )
    projected_comparable, projected_comparable_count = _sum_values(
        item["projected_close_comparable_to_goal"] for item in summaries
    )

    gap = (
        real_comparable - expected
        if real_comparable is not None and expected is not None
        else None
    )
    gap_pct = gap / expected if gap is not None and expected is not None and expected > 0 else None

    comparable_goal_values = [
        item["goal_month"]
        for item in summaries
        if item["projected_close_comparable_to_goal"] is not None
        and item["goal_month"] is not None
    ]
    comparable_goal, comparable_goal_count = _sum_values(comparable_goal_values)
    projected_gap = (
        projected_comparable - comparable_goal
        if projected_comparable is not None and comparable_goal is not None
        else None
    )
    projected_attainment = (
        projected_comparable / comparable_goal
        if projected_comparable is not None
        and comparable_goal is not None
        and comparable_goal > 0
        else None
    )
    remaining = (
        max(goal_month - real_comparable, Decimal("0"))
        if goal_month is not None and real_comparable is not None
        else None
    )
    remaining_days = (
        common_remaining_days
        if common_remaining_days is not None
        else int(summaries[0]["remaining_days"])
        if summaries
        else 0
    )
    required_average = (
        remaining / Decimal(remaining_days)
        if remaining is not None and remaining_days > 0
        else None
    )

    coverage_counts = {
        "goal_month": goal_count,
        "real_mtd": real_count,
        "real_mtd_comparable_to_goal": real_comparable_count,
        "goal_expected_mtd_at_cutoff": expected_count,
        "gap_vs_goal_pace": min(real_comparable_count, expected_count),
        "gap_vs_goal_pace_pct": min(real_comparable_count, expected_count),
        "projected_close": projected_count,
        "projected_close_comparable_to_goal": projected_comparable_count,
        "projected_gap_to_goal": min(projected_comparable_count, comparable_goal_count),
        "projected_goal_attainment_pct": min(
            projected_comparable_count, comparable_goal_count
        ),
        "remaining_to_goal": min(goal_count, real_comparable_count),
        "required_daily_average": min(goal_count, real_comparable_count),
    }
    return {
        "branch_count": len(results),
        "goal_month": goal_month,
        "real_mtd": real_mtd,
        "real_mtd_comparable_to_goal": real_comparable,
        "goal_expected_mtd_at_cutoff": expected,
        "gap_vs_goal_pace": gap,
        "gap_vs_goal_pace_pct": gap_pct,
        "projected_close": projected,
        "projected_close_comparable_to_goal": projected_comparable,
        "projected_gap_to_goal": projected_gap,
        "projected_goal_attainment_pct": projected_attainment,
        "remaining_to_goal": remaining,
        "remaining_days": remaining_days,
        "required_daily_average": required_average,
        "metric_coverage": {
            key: _metric_coverage(eligible=eligible, included=count)
            for key, count in coverage_counts.items()
        },
    }


def aggregate_forecast_center_series(
    results: Sequence[BranchForecastCenterResult],
    *,
    target_month: date,
) -> dict[str, Any]:
    days_in_month = monthrange(target_month.year, target_month.month)[1]
    output: dict[str, Any] = {}
    for series_key in ("actual", "required", "projected"):
        points_by_branch = [
            {point["date"]: point for point in result.series[series_key]}
            for result in results
        ]
        aggregate_points: list[dict[str, Any]] = []
        for day in range(1, days_in_month + 1):
            point_date = date(target_month.year, target_month.month, day)
            daily_values: list[Decimal] = []
            cumulative_values: list[Decimal] = []
            reasons: Counter[str] = Counter()
            included = 0
            for branch_points in points_by_branch:
                point = branch_points.get(point_date)
                if point is None:
                    reasons["missing_date"] += 1
                    continue
                point_status = str(point.get("status") or "")
                if series_key == "actual" and point_status not in {
                    "available",
                    "available_with_negative_adjustment",
                }:
                    reasons[point_status or "unavailable"] += 1
                    continue
                daily = _decimal(point.get("daily"))
                cumulative = _decimal(point.get("cumulative"))
                if series_key == "projected" and point_status == "cutoff_anchor":
                    daily = Decimal("0")
                if daily is None or cumulative is None:
                    reasons["missing_value"] += 1
                    continue
                daily_values.append(daily)
                cumulative_values.append(cumulative)
                included += 1
            expected = len(results)
            aggregate_points.append(
                {
                    "date": point_date,
                    "day": day,
                    "daily": sum(daily_values, Decimal("0")) if daily_values else None,
                    "cumulative": (
                        sum(cumulative_values, Decimal("0"))
                        if cumulative_values
                        else None
                    ),
                    "status": _metric_status(eligible=expected, included=included),
                    "expected_branches": expected,
                    "included_branches": included,
                    "excluded_branches": max(expected - included, 0),
                    "exclusion_reasons": dict(sorted(reasons.items())),
                }
            )
        included_counts = [point["included_branches"] for point in aggregate_points]
        if not included_counts or max(included_counts, default=0) == 0:
            status: MetricStatus = "unavailable"
        elif min(included_counts) == len(results):
            status = "available"
        else:
            status = "partial"
        output[series_key] = {"status": status, "points": aggregate_points}
    return output


def _build_breakdown(
    *,
    results: Sequence[BranchForecastCenterResult],
    dimension: str,
    total_summary: dict[str, Any],
) -> dict[str, Any]:
    if dimension == "none":
        return {"dimension": "none", "items": []}
    groups: dict[str, list[BranchForecastCenterResult]] = defaultdict(list)
    labels: dict[str, str] = {}
    for result in results:
        if dimension == "branch":
            key = str(result.identity["sucursal_canon"])
            labels[key] = str(result.identity["label"])
        elif dimension == "cohort":
            key = str(result.identity["cohort"])
            if key not in {
                TRACK_BRANCH_COHORT_LEGACY_21,
                TRACK_BRANCH_COHORT_NEW_GYMS,
            }:
                continue
            labels[key] = PUBLIC_COHORT_LABELS[key]
        elif dimension == "region":
            key = str(result.identity.get("region_key") or "")
            if not key:
                continue
            labels[key] = key
        else:
            raise ForecastCenterValidationError("breakdown inválido.")
        groups[key].append(result)

    total_real = total_summary.get("real_mtd")
    total_projected_gap = total_summary.get("projected_gap_to_goal")
    items: list[dict[str, Any]] = []
    for key in sorted(groups):
        group = groups[key]
        summary = aggregate_forecast_center_results(group)
        real = summary.get("real_mtd")
        projected_gap = summary.get("projected_gap_to_goal")
        drilldown: dict[str, Any] = {"scope": dimension, "scope_id": key}
        if dimension == "branch":
            drilldown = dict(group[0].drilldown)
        items.append(
            {
                "key": key,
                "label": labels[key],
                "dimension": dimension,
                "branch_count": len(group),
                "summary": {
                    field: value
                    for field, value in summary.items()
                    if field not in {"metric_coverage", "branch_count"}
                },
                "metric_coverage": summary["metric_coverage"],
                "quality_status": _overall_quality_status(group, len(group)),
                "contribution": {
                    "real_mtd_share": (
                        real / total_real
                        if real is not None and total_real is not None and total_real != 0
                        else None
                    ),
                    "projected_gap_share": (
                        projected_gap / total_projected_gap
                        if projected_gap is not None
                        and total_projected_gap is not None
                        and total_projected_gap != 0
                        else None
                    ),
                },
                "drilldown": drilldown,
            }
        )
    return {"dimension": dimension, "items": items}


def _overall_quality_status(
    results: Sequence[BranchForecastCenterResult],
    selected_count: int,
) -> MetricStatus:
    if not results:
        return "unavailable"
    fully_available = sum(
        1
        for result in results
        if result.summary.get("real_mtd") is not None
        and result.summary.get("goal_month") is not None
        and result.summary.get("projected_close") is not None
        and not result.quality.get("has_daily_gaps")
    )
    if fully_available == selected_count:
        return "available"
    return "partial"


def _build_quality(
    *,
    selected_branches: Sequence[ForecastCenterBranch],
    results: Sequence[BranchForecastCenterResult],
    universe: ForecastCenterUniverse,
    bundle: ForecastCenterBulkBundle,
    access: ForecastCenterAccess,
    resolved_version: Any,
) -> dict[str, Any]:
    summary = aggregate_forecast_center_results(
        results, eligible_branch_count=len(selected_branches)
    )
    known_goal = summary["goal_month"]
    goal_with_projection, _ = _sum_values(
        result.summary["goal_month"]
        for result in results
        if result.summary["projected_close"] is not None
    )
    real_with_projection, _ = _sum_values(
        result.summary["real_mtd"]
        for result in results
        if result.summary["projected_close"] is not None
    )
    real_total = summary["real_mtd"]
    selected_canons = {branch.sucursal_canon for branch in selected_branches}
    visible_exclusions = [
        item.to_dict()
        for item in universe.exclusions
        if access.is_global
        or item.sucursal_canon is None
        or item.sucursal_canon in selected_canons
    ]
    for branch in selected_branches:
        if branch.sucursal_canon not in bundle.mart_by_branch:
            visible_exclusions.append(
                ForecastCenterExclusion(
                    sucursal_canon=branch.sucursal_canon,
                    reasons=("missing_track_version_row",),
                    stage="track_version",
                    affects_metrics=("all",),
                ).to_dict()
            )
    fallbacks: list[dict[str, Any]] = []
    if access.fallback_used:
        fallbacks.append(
            {
                "type": "authorization",
                "reason": access.fallback_reason,
            }
        )
    calendar_fallback_branches = [
        result.identity["sucursal_canon"]
        for result in results
        if result.quality["has_calendar_fallback"]
    ]
    if calendar_fallback_branches:
        fallbacks.append(
            {
                "type": "calendar",
                "reason": "last_weekday_occurrence_fallback",
                "branch_count": len(calendar_fallback_branches),
                "branches": calendar_fallback_branches,
            }
        )
    return {
        "status": _overall_quality_status(results, len(selected_branches)),
        "branches": {
            "selected": len(selected_branches),
            "included": len(results),
            "with_track_row": len(results),
            "with_goal": sum(
                result.summary["goal_month"] is not None for result in results
            ),
            "with_history": sum(
                result.quality["history_status"] == "available" for result in results
            ),
            "with_projection": sum(
                result.summary["projected_close"] is not None for result in results
            ),
            "with_calendar_fallback": len(calendar_fallback_branches),
            "with_daily_gaps": sum(
                bool(result.quality["has_daily_gaps"]) for result in results
            ),
            "without_region": sum(
                result.identity.get("region_key") is None for result in results
            ),
            "unauthorized_removed": universe.unauthorized_removed,
        },
        "monetary_coverage": {
            "known_goal_amount": known_goal,
            "goal_amount_with_projection": goal_with_projection,
            "projection_vs_known_goal_pct": (
                goal_with_projection / known_goal
                if goal_with_projection is not None
                and known_goal is not None
                and known_goal > 0
                else None
            ),
            "real_amount_total": real_total,
            "real_amount_comparable_to_goal": summary[
                "real_mtd_comparable_to_goal"
            ],
            "real_amount_with_projection": real_with_projection,
            "projection_real_coverage_pct": (
                real_with_projection / real_total
                if real_with_projection is not None
                and real_total is not None
                and real_total > 0
                else None
            ),
        },
        "exclusions": visible_exclusions,
        "fallbacks": fallbacks,
        "cutoff": {
            "track_daily_version_id": int(resolved_version.id),
            "version_type": str(resolved_version.version_type),
            "status": str(resolved_version.status),
            "canonical_snapshot_id": bundle.canonical_snapshot_id,
            "canonical_business_date": bundle.canonical_business_date,
        },
        "methodology": {
            "projection_formula": "projected_close = real_mtd / historical_progress_pct",
            "calendar_method": "weekday_ordinal_aligned_historical_weights",
            "goal_basis": "total_mtd",
            "distribution_basis": "venta_total_base",
            "aggregadoras_assumed_same_daily_shape": True,
            "aggregate_method": "sum_branch_forecasts",
        },
        "loader_invocations": bundle.loader_invocations,
    }


def _default_breakdown(scope: str) -> str:
    return {
        "national": "cohort",
        "region": "branch",
        "authorized_pool": "branch",
        "branch": "none",
    }[scope]


def build_forecast_center(
    *,
    user: Any,
    requested_track_date: date,
    generation_mode: str,
    resolved_version: Any,
    scope: str,
    scope_id: str | None,
    cohort: str = "all",
    breakdown: str | None = None,
) -> dict[str, Any]:
    access = resolve_forecast_center_access(user)
    normalized_scope = str(scope or "").strip().lower()
    normalized_cohort = str(cohort or "all").strip().lower()
    if normalized_scope not in CENTER_SCOPES:
        raise ForecastCenterValidationError("scope inválido.")
    normalized_breakdown = str(
        breakdown or _default_breakdown(normalized_scope)
    ).strip().lower()
    if normalized_breakdown not in CENTER_BREAKDOWNS:
        raise ForecastCenterValidationError("breakdown inválido.")
    universe = resolve_forecast_center_universe(
        access=access,
        requested_track_date=requested_track_date,
    )
    selected = select_forecast_center_scope(
        universe=universe,
        access=access,
        scope=normalized_scope,
        scope_id=scope_id,
        cohort=normalized_cohort,
    )
    bundle = bulk_load_forecast_center_data(
        branches=selected,
        track_date=requested_track_date,
        track_daily_version_id=int(resolved_version.id),
    )
    results: list[BranchForecastCenterResult] = []
    for branch in selected:
        if branch.sucursal_canon not in bundle.mart_by_branch:
            continue
        result = calculate_compact_branch_forecast(
            branch=branch,
            bundle=bundle,
            track_date=requested_track_date,
            track_daily_version_id=int(resolved_version.id),
        )
        if result is not None:
            results.append(result)

    summary = aggregate_forecast_center_results(
        results,
        eligible_branch_count=len(selected),
        common_remaining_days=(
            monthrange(requested_track_date.year, requested_track_date.month)[1]
            - requested_track_date.day
        ),
    )
    target_month = _first_day_of_month(requested_track_date)
    return {
        "status": "ok",
        "context": {
            "requested_track_date": requested_track_date,
            "resolved_track_date": resolved_version.track_date,
            "target_month": target_month,
            "generation_mode": generation_mode,
            "scope": normalized_scope,
            "scope_id": (
                selected[0].sucursal_canon
                if normalized_scope == "branch" and selected and not scope_id
                else scope_id
            ),
            "cohort": normalized_cohort,
            "user_access_scope": access.to_public_dict(),
            "resolved_version": {
                "id": int(resolved_version.id),
                "version_type": str(resolved_version.version_type),
                "status": str(resolved_version.status),
                "generated_at_utc": resolved_version.generated_at_utc,
            },
        },
        "summary": summary,
        "series": aggregate_forecast_center_series(
            results,
            target_month=target_month,
        ),
        "breakdown": _build_breakdown(
            results=results,
            dimension=normalized_breakdown,
            total_summary=summary,
        ),
        "quality": _build_quality(
            selected_branches=selected,
            results=results,
            universe=universe,
            bundle=bundle,
            access=access,
            resolved_version=resolved_version,
        ),
    }


def build_forecast_center_catalogs(
    *,
    user: Any,
    requested_track_date: date,
) -> dict[str, Any]:
    access = resolve_forecast_center_access(user)
    universe = resolve_forecast_center_universe(
        access=access,
        requested_track_date=requested_track_date,
    )
    role = access.role
    if access.is_global:
        scopes = ["national", "region", "branch"]
        default_scope = "national"
        default_scope_id = None
        cohorts = ["all", TRACK_BRANCH_COHORT_LEGACY_21, TRACK_BRANCH_COHORT_NEW_GYMS]
    elif role == "GERENTE_REGIONAL":
        scopes = ["authorized_pool", "region", "branch"]
        default_scope = "authorized_pool"
        default_scope_id = None
        cohorts = ["all", TRACK_BRANCH_COHORT_LEGACY_21, TRACK_BRANCH_COHORT_NEW_GYMS]
    else:
        scopes = ["branch"]
        default_scope = "branch"
        default_scope_id = (
            universe.branches[0].sucursal_canon if len(universe.branches) == 1 else None
        )
        cohorts = ["all"]

    visible_region_counts: Counter[str] = Counter(
        branch.region_key for branch in universe.branches if branch.region_key
    )
    region_labels = {
        branch.region_key: branch.region_label
        for branch in universe.branches
        if branch.region_key
    }
    regions = [
        {
            "region_key": key,
            "label": region_labels[key],
            "authorized_branch_count": count,
            "total_region_branch_count": universe.total_region_branch_counts.get(key, count),
            "is_partial_access": count < universe.total_region_branch_counts.get(key, count),
        }
        for key, count in sorted(visible_region_counts.items())
    ]
    definitions = {
        item["key"]: item for item in get_track_branch_cohort_definitions()
    }
    cohort_items = []
    for key in cohorts:
        if key == "all":
            cohort_items.append({"key": "all", "label": "Total Ultra"})
        else:
            cohort_items.append(
                {
                    "key": key,
                    "label": PUBLIC_COHORT_LABELS.get(
                        key, definitions.get(key, {}).get("label", key)
                    ),
                }
            )
    return {
        "status": "ok",
        "context": {
            "user_access_scope": access.to_public_dict(),
            "default_scope": default_scope,
            "default_scope_id": default_scope_id,
            "default_cohort": "all",
            "default_generation_mode": "manual_preview",
        },
        "capabilities": {
            "can_view_national": access.is_global,
            "can_view_regions": access.is_global or role == "GERENTE_REGIONAL",
            "can_view_authorized_pool": role == "GERENTE_REGIONAL",
            "can_view_branches": True,
            "can_drilldown": True,
            "can_view_methodology": True,
        },
        "scopes": [{"key": key, "label": key} for key in scopes],
        "cohorts": cohort_items,
        "regions": regions,
        "branches": [
            {
                "sucursal_canon": branch.sucursal_canon,
                "sucursal_id": branch.sucursal_id,
                "label": branch.label,
                "cohort": branch.cohort,
                "region_key": branch.region_key,
                "operational_status": branch.operational_status,
            }
            for branch in universe.branches
        ],
        "generation_modes": ["manual_preview", "official_closed_day"],
    }
