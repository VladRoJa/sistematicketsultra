from __future__ import annotations

from typing import Iterable

from app.models.warehouse import TrackBranchCatalogORM
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


def marketing_branch_keys_by_sucursal_ids(
    *,
    sucursal_ids: Iterable[int],
    session,
) -> dict[int, str]:
    """Map Suite branch IDs to canonical Track branch keys without legacy campaign semantics."""

    ids = tuple(
        sorted(
            {
                int(value)
                for value in sucursal_ids
                if value is not None
            }
        )
    )
    if not ids:
        return {}

    rows = (
        session.query(TrackBranchCatalogORM)
        .filter(
            TrackBranchCatalogORM.is_track_active.is_(True),
            TrackBranchCatalogORM.sucursal_id.in_(ids),
        )
        .all()
    )
    result: dict[int, str] = {}
    for row in rows:
        if row.sucursal_id is None:
            continue
        key = normalize_socios_vencidos_branch_key(row.track_label)
        if key is not None:
            result[int(row.sucursal_id)] = key
    return result
