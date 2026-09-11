from __future__ import annotations

from app.extensions import db
from app.models.sucursal_model import Sucursal, SucursalOperationalStatus
from app.models.warehouse import TrackBranchCatalogORM
from app.warehouse.services.track_branch_cohort_service import (
    normalize_track_branch_canon,
    resolve_track_branch_cohort_from_display_order,
)


EXCLUDED_BRANCHES = {
    "CORPORATIVO",
    "GIMNASIO PRUEBA",
    "LA_VIGA",
}


def load_operational_track_branch_canons() -> set[str]:
    rows = (
        db.session.query(TrackBranchCatalogORM, Sucursal)
        .join(
            Sucursal,
            Sucursal.sucursal_id == TrackBranchCatalogORM.sucursal_id,
        )
        .filter(
            TrackBranchCatalogORM.is_track_active.is_(True),
            Sucursal.operational_status == SucursalOperationalStatus.ACTIVA,
        )
        .all()
    )

    operational_canons: set[str] = set()

    for catalog, _sucursal in rows:
        canon = normalize_track_branch_canon(catalog.sucursal_canon)

        if not canon:
            continue

        if canon in EXCLUDED_BRANCHES:
            continue

        if resolve_track_branch_cohort_from_display_order(
            catalog.display_order
        ) is None:
            continue

        operational_canons.add(canon)

    return operational_canons