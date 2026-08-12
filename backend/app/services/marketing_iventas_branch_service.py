"""Resolución dinámica de sucursales iVentas hacia Track.

Este módulo conoce ORM únicamente para resolver:

branch_code iVentas
    -> TrackBranchAliasORM / iventas_family
    -> sucursal_canon
    -> TrackBranchCatalogORM
    -> sucursal_id

No contiene diccionarios de negocio hardcodeados.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.warehouse import (
    TrackBranchCatalogORM,
)
from app.warehouse.services.track_branch_alias_resolver_service import (
    resolve_track_branch_alias,
)


IVENTAS_ALIAS_SOURCE_FAMILY = "iventas_family"


class MarketingIventasBranchResolutionError(
    RuntimeError
):
    """Inconsistencia estructural al resolver sucursal iVentas."""


@dataclass(frozen=True)
class MarketingIventasBranchResolution:
    """Resultado canónico de una sucursal iVentas."""

    branch_code: str
    sucursal_canon: str
    sucursal_id: int


def resolve_iventas_branch(
    branch_code: Any,
) -> MarketingIventasBranchResolution | None:
    """Resuelve un código iVentas mediante aliases Track activos.

    Retorna None cuando el código iVentas no tiene alias activo.

    Lanza error cuando existe alias pero su destino Track
    está inconsistente, inactivo o carece de sucursal_id.
    """

    normalized_branch_code = str(
        branch_code or ""
    ).strip()

    if not normalized_branch_code:
        raise ValueError(
            "branch_code no puede estar vacío."
        )

    sucursal_canon = resolve_track_branch_alias(
        source_family=IVENTAS_ALIAS_SOURCE_FAMILY,
        raw_branch_name=normalized_branch_code,
    )

    if sucursal_canon is None:
        return None

    catalog = _load_track_catalog_branch(
        sucursal_canon
    )

    if catalog is None:
        raise MarketingIventasBranchResolutionError(
            "El alias iVentas resolvió a "
            f"{sucursal_canon!r}, pero no existe "
            "una fila única en track_branch_catalog."
        )

    if catalog.sucursal_id is None:
        raise MarketingIventasBranchResolutionError(
            "El destino Track "
            f"{sucursal_canon!r} no tiene sucursal_id."
        )

    if not bool(catalog.is_track_active):
        raise MarketingIventasBranchResolutionError(
            "El destino Track "
            f"{sucursal_canon!r} está inactivo."
        )

    sucursal_id = int(
        catalog.sucursal_id
    )

    if sucursal_id <= 0:
        raise MarketingIventasBranchResolutionError(
            "El destino Track "
            f"{sucursal_canon!r} tiene "
            "sucursal_id inválido."
        )

    return MarketingIventasBranchResolution(
        branch_code=normalized_branch_code,
        sucursal_canon=str(
            sucursal_canon
        ).strip(),
        sucursal_id=sucursal_id,
    )


def _load_track_catalog_branch(
    sucursal_canon: str,
):
    """Carga exactamente una fila del catálogo Track."""

    rows = (
        TrackBranchCatalogORM.query
        .filter(
            TrackBranchCatalogORM.sucursal_canon
            == sucursal_canon
        )
        .all()
    )

    if len(rows) != 1:
        return None

    return rows[0]
