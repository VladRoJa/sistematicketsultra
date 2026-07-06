from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.warehouse import TrackBranchCatalogORM


TRACK_LEGACY_21_MAX_DISPLAY_ORDER = 21

TRACK_BRANCH_COHORT_LEGACY_21 = "legacy_21"
TRACK_BRANCH_COHORT_NEW_GYMS = "new_gyms"
TRACK_BRANCH_COHORT_TOTAL_ULTRA = "total_ultra"


@dataclass(frozen=True)
class TrackBranchCohortDefinition:
    key: str
    label: str
    description: str
    display_order: int


def normalize_track_branch_canon(value: Any) -> str:
    return str(value or "").strip().upper()


def get_track_branch_cohort_definitions() -> list[dict[str, Any]]:
    return [
        {
            "key": TRACK_BRANCH_COHORT_LEGACY_21,
            "label": "ULTRA 21",
            "description": "Sucursales históricas Ultra con display_order del 1 al 21.",
            "display_order": 1,
        },
        {
            "key": TRACK_BRANCH_COHORT_NEW_GYMS,
            "label": "ULTRA NUEVOS",
            "description": "Sucursales nuevas Ultra con display_order mayor a 21.",
            "display_order": 2,
        },
        {
            "key": TRACK_BRANCH_COHORT_TOTAL_ULTRA,
            "label": "ULTRA TOTAL",
            "description": "Total Ultra combinando sucursales históricas y nuevas.",
            "display_order": 3,
        },
    ]


def resolve_track_branch_cohort_from_display_order(display_order: Any) -> str | None:
    if display_order is None:
        return None

    try:
        normalized_display_order = int(display_order)
    except (TypeError, ValueError):
        return None

    if normalized_display_order <= TRACK_LEGACY_21_MAX_DISPLAY_ORDER:
        return TRACK_BRANCH_COHORT_LEGACY_21

    return TRACK_BRANCH_COHORT_NEW_GYMS


def build_track_branch_cohort_lookup(
    *,
    sucursales_canon: set[str] | list[str] | tuple[str, ...] | None = None,
    active_only: bool = True,
) -> dict[str, str]:
    query = TrackBranchCatalogORM.query

    if active_only:
        query = query.filter(TrackBranchCatalogORM.is_track_active.is_(True))

    normalized_canons = {
        normalize_track_branch_canon(value)
        for value in (sucursales_canon or [])
        if normalize_track_branch_canon(value)
    }

    if normalized_canons:
        query = query.filter(TrackBranchCatalogORM.sucursal_canon.in_(normalized_canons))

    rows = query.all()

    lookup: dict[str, str] = {}

    for row in rows:
        sucursal_canon = normalize_track_branch_canon(row.sucursal_canon)
        cohort_key = resolve_track_branch_cohort_from_display_order(row.display_order)

        if not sucursal_canon or not cohort_key:
            continue

        lookup[sucursal_canon] = cohort_key

    return lookup


def get_track_branch_cohort_key(
    *,
    sucursal_canon: str,
    cohort_lookup: dict[str, str],
) -> str | None:
    normalized_canon = normalize_track_branch_canon(sucursal_canon)

    if not normalized_canon:
        return None

    return cohort_lookup.get(normalized_canon)


def get_track_branch_cohort_label(cohort_key: str) -> str:
    definitions = {
        item["key"]: item["label"]
        for item in get_track_branch_cohort_definitions()
    }

    return definitions.get(cohort_key, cohort_key)
