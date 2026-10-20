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


class CampaignV2DispatchBranchResolver:
    """Request-scoped branch index: catalog and aliases are queried only once.

    Keep this instance local to an operation. No process-wide cache is used;
    a new preflight observes current canonical catalogs and aliases.
    """

    def __init__(self, *, session: Any | None = None) -> None:
        self._session = session if session is not None else db.session
        self._candidates: dict[str, dict[str, Any]] | None = None

    def _load_candidates(self) -> dict[str, dict[str, Any]]:
        catalogs = (
            self._session.query(TrackBranchCatalogORM)
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
        candidates: dict[str, dict[str, Any]] = {}
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
            for value in match_values:
                if value:
                    candidates.setdefault(value, {})[str(row.sucursal_canon)] = row

        aliases = (
            self._session.query(TrackBranchAliasORM)
            .filter(TrackBranchAliasORM.is_active.is_(True))
            .all()
        )
        for alias in aliases:
            raw_key = normalize_socios_vencidos_branch_key(alias.raw_branch_name)
            catalog = by_canon.get(str(alias.sucursal_canon))
            if raw_key and catalog is not None:
                candidates.setdefault(raw_key, {})[str(catalog.sucursal_canon)] = catalog
        return candidates

    def resolve(self, branch_key: Any) -> MarketingCampaignV2DispatchBranch | None:
        normalized = normalize_socios_vencidos_branch_key(branch_key)
        if not normalized:
            return None
        if self._candidates is None:
            self._candidates = self._load_candidates()
        matches = self._candidates.get(normalized, {})
        if len(matches) != 1:
            return None
        catalog = next(iter(matches.values()))
        return MarketingCampaignV2DispatchBranch(
            sucursal_id=int(catalog.sucursal_id),
            sucursal_canon=str(catalog.sucursal_canon),
            track_label=str(catalog.track_label),
            matched_key=normalized,
        )


def resolve_frozen_recipient_branch(
    recipient: Any,
    *,
    session: Any | None = None,
    resolver: CampaignV2DispatchBranchResolver | None = None,
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

    branch_key = next(iter(keys))
    if resolver is not None:
        return resolver.resolve(branch_key)
    return resolve_dispatch_branch_key(branch_key, session=session)


def resolve_dispatch_branch_key(
    branch_key: Any,
    *,
    session: Any | None = None,
) -> MarketingCampaignV2DispatchBranch | None:
    """Resolve one key with the same canonical/ambiguity rules as preflight."""
    return CampaignV2DispatchBranchResolver(session=session).resolve(branch_key)
