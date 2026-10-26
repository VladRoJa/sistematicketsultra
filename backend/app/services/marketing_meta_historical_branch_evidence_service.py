"""Read-only monthly Warehouse evidence for historical Meta city splitting.

This resolver is isolated: it never allocates spend, changes canonical data,
or participates in the current iVentas attribution flow. Inputs are canonical
KPI Desempeño daily snapshots, active Gasca/Track branch aliases and the
gym branch catalogue. Missing/conflicting evidence fails closed.

Only month-level presence is established, NOT an exact opening/closing date.
The city_key must already be normalized by a separate Meta identity resolver;
never pass an unreviewed ad-set label directly to this function.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
import re
import unicodedata
from typing import Iterable

from sqlalchemy import select

from app.extensions import db
from app.models.sucursal_model import Sucursal
from app.models.openings import OpeningORM, OpeningStatus
from app.models.warehouse import (
    KpiDesempenoSnapshotORM,
    KpiDesempenoSnapshotRowORM,
    TrackBranchAliasORM,
    TrackBranchCatalogORM,
)
from app.services.marketing_meta_historical_allocation_service import (
    RESERVED_NON_GYM_BRANCH_IDS,
)


GASCA_FAMILY = "gasca_family"
VERIFIED = "VERIFIED"
NO_CANONICAL_SNAPSHOT = "NO_CANONICAL_SNAPSHOT"
NO_CITY_IN_CATALOG = "NO_CITY_IN_CATALOG"
NO_CITY_EVIDENCE = "NO_CITY_EVIDENCE"
REQUIRES_REVIEW = "REQUIRES_REVIEW"
PREOPENING_ONLY = "PREOPENING_ONLY"

# KPI Desempeño explicitly treats BECA as out of scope.
OUT_OF_SCOPE_RAW_BRANCHES = frozenset({"BECA"})


@dataclass(frozen=True)
class HistoricalCityBranchEvidence:
    month_start: date
    city_key: str
    status: str
    eligible_branch_ids: tuple[int, ...]
    snapshot_ids: tuple[int, ...]
    observed_branch_names: tuple[str, ...]
    unresolved_branch_names: tuple[str, ...]
    excluded_preopening_branch_ids: tuple[int, ...] = ()
    opening_review_branch_ids: tuple[int, ...] = ()
    opening_date_unrecorded_branch_ids: tuple[int, ...] = ()


def _normalize(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("El nombre debe ser texto.")
    unaccented = "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[\s_]+", " ", unaccented.upper().strip()).split())


def _validate_month_and_city(month_start: date, city_key: str) -> str:
    if type(month_start) is not date or month_start.day != 1:
        raise ValueError("month_start debe ser el primer día del mes.")
    normalized_city = _normalize(city_key)
    if not normalized_city:
        raise ValueError("city_key es obligatorio.")
    return normalized_city


def build_canonical_kpi_month_statement(*, month_start: date):
    """Select only canonical daily KPI snapshots inside the exact month."""
    _validate_month_and_city(month_start, "VALIDATION")
    month_end = date(
        month_start.year,
        month_start.month,
        monthrange(month_start.year, month_start.month)[1],
    )
    return (
        select(KpiDesempenoSnapshotORM.id)
        .where(
            KpiDesempenoSnapshotORM.report_type_key == "kpi_desempeno",
            KpiDesempenoSnapshotORM.snapshot_kind == "daily",
            KpiDesempenoSnapshotORM.is_canonical.is_(True),
            KpiDesempenoSnapshotORM.business_date >= month_start,
            KpiDesempenoSnapshotORM.business_date <= month_end,
        )
        .order_by(KpiDesempenoSnapshotORM.id)
    )


def evaluate_historical_city_branch_evidence(
    *,
    month_start: date,
    city_key: str,
    snapshot_ids: Iterable[int],
    raw_branch_names: Iterable[str],
    gasca_aliases: Iterable[tuple[str, int]],
    catalog_branches: Iterable[tuple[int, str, bool]],
    opening_records: Iterable[tuple[int, date | None, str]] = (),
) -> HistoricalCityBranchEvidence:
    """Resolve only gyms witnessed in Warehouse during the requested month.

    All raw KPI branch names need unambiguous canonical aliases, regardless
    of city. Otherwise, incompleteness could silently reduce the denominator.
    An unresolved month is never treated as zero spend or zero gyms.
    A real opening dated after this month excludes that branch even if the
    historical KPI includes pre-sale activity. An opening inside this month
    requires review because a monthly split cannot infer daily eligibility.
    Missing opening records are exposed explicitly: Warehouse evidence alone
    never certifies an actual operating date.
    """
    city = _validate_month_and_city(month_start, city_key)
    ids = tuple(sorted(set(snapshot_ids)))
    names = tuple(sorted({_normalize(name) for name in raw_branch_names}))
    if any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("Snapshot IDs inválidos.")

    def result(status: str, *, eligible=(), unresolved=(), preopening=(), opening_review=(), unrecorded=()):
        return HistoricalCityBranchEvidence(
            month_start=month_start,
            city_key=city,
            status=status,
            eligible_branch_ids=tuple(sorted(eligible)),
            snapshot_ids=ids,
            observed_branch_names=names,
            unresolved_branch_names=tuple(sorted(set(unresolved))),
            excluded_preopening_branch_ids=tuple(sorted(preopening)),
            opening_review_branch_ids=tuple(sorted(opening_review)),
            opening_date_unrecorded_branch_ids=tuple(sorted(unrecorded)),
        )

    if not ids:
        return result(NO_CANONICAL_SNAPSHOT)

    branch_city_by_id: dict[int, str] = {}
    demo_ids: set[int] = set()
    for branch_id, municipality, is_demo in catalog_branches:
        if type(branch_id) is not int or branch_id <= 0:
            raise ValueError("ID inválido en catálogo de sucursales.")
        current_city = _normalize(municipality)
        if branch_id in branch_city_by_id and branch_city_by_id[branch_id] != current_city:
            raise ValueError("Ciudad contradictoria para una sucursal.")
        branch_city_by_id[branch_id] = current_city
        if is_demo:
            demo_ids.add(branch_id)

    eligible_city_ids = {
        branch_id
        for branch_id, municipality in branch_city_by_id.items()
        if municipality == city
        and branch_id not in RESERVED_NON_GYM_BRANCH_IDS
        and branch_id not in demo_ids
    }
    if not eligible_city_ids:
        return result(NO_CITY_IN_CATALOG)

    alias_ids: dict[str, int] = {}
    conflicting_aliases: set[str] = set()
    for raw_name, branch_id in gasca_aliases:
        name = _normalize(raw_name)
        if not name:
            continue
        if type(branch_id) is not int or branch_id <= 0:
            conflicting_aliases.add(name)
            continue
        previous_id = alias_ids.get(name)
        if previous_id is not None and previous_id != branch_id:
            conflicting_aliases.add(name)
        else:
            alias_ids[name] = branch_id

    unresolved_names = {
        name
        for name in names
        if name not in OUT_OF_SCOPE_RAW_BRANCHES
        and (
            name not in alias_ids
            or name in conflicting_aliases
            or alias_ids[name] not in branch_city_by_id
        )
    }
    if unresolved_names:
        return result(REQUIRES_REVIEW, unresolved=unresolved_names)

    observed_ids = {
        alias_ids[name]
        for name in names
        if name not in OUT_OF_SCOPE_RAW_BRANCHES
    }
    matches = observed_ids & eligible_city_ids
    month_end = date(
        month_start.year,
        month_start.month,
        monthrange(month_start.year, month_start.month)[1],
    )
    openings: dict[int, tuple[date | None, str]] = {}
    duplicates: set[int] = set()
    for branch_id, actual_date, opening_status in opening_records:
        if type(branch_id) is not int or branch_id <= 0:
            raise ValueError("ID inválido en el registro de aperturas.")
        if actual_date is not None and type(actual_date) is not date:
            raise ValueError("Fecha real de apertura inválida.")
        if not isinstance(opening_status, str):
            raise ValueError("Estado de apertura inválido.")
        if branch_id in openings:
            duplicates.add(branch_id)
        openings[branch_id] = (actual_date, opening_status)

    excluded_preopening = set()
    opening_review = set()
    for branch_id in matches:
        if branch_id in duplicates:
            opening_review.add(branch_id)
            continue
        record = openings.get(branch_id)
        if record is None:
            continue
        opening_date, status = record
        if status != OpeningStatus.OPENED or opening_date is None:
            opening_review.add(branch_id)
        elif opening_date > month_end:
            excluded_preopening.add(branch_id)
        elif opening_date >= month_start:
            opening_review.add(branch_id)

    if opening_review:
        return result(
            REQUIRES_REVIEW,
            preopening=excluded_preopening,
            opening_review=opening_review,
        )

    eligible = matches - excluded_preopening
    return result(
        VERIFIED if eligible else (
            PREOPENING_ONLY if excluded_preopening else NO_CITY_EVIDENCE
        ),
        eligible=eligible,
        preopening=excluded_preopening,
        unrecorded=eligible - set(openings),
    )


def read_historical_city_branch_evidence(
    *,
    month_start: date,
    city_key: str,
    session=None,
) -> HistoricalCityBranchEvidence:
    """Load the strictly read-only Warehouse evidence for a city and month.

    Must be called only from an authorized internal/global analysis path.
    A future scoped Funnel adapter must apply access restrictions separately.
    """
    _validate_month_and_city(month_start, city_key)
    session_value = db.session if session is None else session
    ids = tuple(
        int(row_id)
        for row_id in session_value.execute(
            build_canonical_kpi_month_statement(month_start=month_start)
        ).scalars().all()
    )
    if not ids:
        return evaluate_historical_city_branch_evidence(
            month_start=month_start,
            city_key=city_key,
            snapshot_ids=(),
            raw_branch_names=(),
            gasca_aliases=(),
            catalog_branches=(),
        )

    raw_names = session_value.execute(
        select(KpiDesempenoSnapshotRowORM.sucursal)
        .where(KpiDesempenoSnapshotRowORM.snapshot_id.in_(ids))
        .distinct()
    ).scalars().all()

    aliases = session_value.execute(
        select(
            TrackBranchAliasORM.raw_branch_name,
            TrackBranchCatalogORM.sucursal_id,
        )
        .join(
            TrackBranchCatalogORM,
            TrackBranchCatalogORM.sucursal_canon
            == TrackBranchAliasORM.sucursal_canon,
        )
        .where(
            TrackBranchAliasORM.source_family == GASCA_FAMILY,
            TrackBranchAliasORM.is_active.is_(True),
            TrackBranchCatalogORM.sucursal_id.is_not(None),
        )
    ).all()

    branches = session_value.execute(
        select(Sucursal.sucursal_id, Sucursal.municipio, Sucursal.is_demo)
    ).all()

    openings = session_value.execute(
        select(
            OpeningORM.sucursal_id,
            OpeningORM.actual_opening_date,
            OpeningORM.status,
        )
    ).all()

    return evaluate_historical_city_branch_evidence(
        month_start=month_start,
        city_key=city_key,
        snapshot_ids=ids,
        raw_branch_names=raw_names,
        gasca_aliases=aliases,
        catalog_branches=branches,
        opening_records=openings,
    )
