"""Canonical branch resolution for Campaign V2 frozen recipients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.extensions import db
from app.models.warehouse import TrackBranchAliasORM, TrackBranchCatalogORM
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


@dataclass(frozen=True)
class MarketingCampaignV2DispatchBranch:
    sucursal_id: int
    sucursal_canon: str
    track_label: str
    matched_key: str


def resolve_frozen_recipient_branch(
    recipient: Any,
    *,
    session: Any | None = None,
) -> MarketingCampaignV2DispatchBranch | None:
    """Resolve branch only from frozen recipient/evidence plus canonical catalogs."""

    keys = {
        key
        for evidence in (getattr(recipient, "evidence_rows", None) or [])
        if (
            key := normalize_socios_vencidos_branch_key(
                getattr(evidence, "sucursal_key", None)
            )
        )
    }
    if not keys:
        fallback = normalize_socios_vencidos_branch_key(
            getattr(recipient, "sucursal", None)
        )
        if fallback:
            keys.add(fallback)

    if len(keys) != 1:
        return None

    return resolve_dispatch_branch_key(
        next(iter(keys)),
        session=session,
    )


def resolve_dispatch_branch_key(
    branch_key: Any,
    *,
    session: Any | None = None,
) -> MarketingCampaignV2DispatchBranch | None:
    active_session = session if session is not None else db.session
    normalized = normalize_socios_vencidos_branch_key(branch_key)
    if not normalized:
        return None

    catalogs = (
        active_session.query(TrackBranchCatalogORM)
        .filter(
            TrackBranchCatalogORM.is_track_active.is_(True),
            TrackBranchCatalogORM.sucursal_id.isnot(None),
        )
        .all()
    )
    by_canon = {
        str(row.sucursal_canon): row
        for row in catalogs
        if row.sucursal_id is not None
    }

    candidates: dict[str, Any] = {}
    for row in catalogs:
        match_values = {
            normalize_socios_vencidos_branch_key(row.sucursal_canon),
            normalize_socios_vencidos_branch_key(row.track_label),
        }
        suite_branch = getattr(row, "sucursal", None)
        if suite_branch is not None:
            match_values.add(
                normalize_socios_vencidos_branch_key(
                    getattr(suite_branch, "sucursal", None)
                )
            )
        if normalized in {value for value in match_values if value}:
            candidates[str(row.sucursal_canon)] = row

    aliases = (
        active_session.query(TrackBranchAliasORM)
        .filter(TrackBranchAliasORM.is_active.is_(True))
        .all()
    )
    for alias in aliases:
        raw_key = normalize_socios_vencidos_branch_key(alias.raw_branch_name)
        if raw_key != normalized:
            continue
        catalog = by_canon.get(str(alias.sucursal_canon))
        if catalog is not None:
            candidates[str(catalog.sucursal_canon)] = catalog

    if len(candidates) != 1:
        return None

    catalog = next(iter(candidates.values()))
    return MarketingCampaignV2DispatchBranch(
        sucursal_id=int(catalog.sucursal_id),
        sucursal_canon=str(catalog.sucursal_canon),
        track_label=str(catalog.track_label),
        matched_key=normalized,
    )
