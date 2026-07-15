from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.warehouse import TrackBranchAliasORM, TrackBranchCatalogORM


GASCA_SOURCE_FAMILY = "gasca_family"


def resolve_track_alias_sucursal_id(
    source_branch_name: object,
    *,
    session: Any,
    source_family: str,
) -> int | None:
    raw_branch_name = str(source_branch_name or "").strip()
    normalized_source_family = str(source_family or "").strip()
    if not raw_branch_name or not normalized_source_family:
        return None

    statement = (
        select(TrackBranchCatalogORM.sucursal_id)
        .join(
            TrackBranchAliasORM,
            TrackBranchAliasORM.sucursal_canon
            == TrackBranchCatalogORM.sucursal_canon,
        )
        .where(
            TrackBranchAliasORM.source_family == normalized_source_family,
            TrackBranchAliasORM.raw_branch_name == raw_branch_name,
            TrackBranchAliasORM.is_active.is_(True),
        )
        .limit(1)
    )
    sucursal_id = session.execute(statement).scalar_one_or_none()
    if (
        not isinstance(sucursal_id, int)
        or isinstance(sucursal_id, bool)
        or sucursal_id <= 0
    ):
        return None
    return sucursal_id


def resolve_gasca_branch_id(
    source_branch_name: object,
    *,
    session: Any,
) -> int | None:
    return resolve_track_alias_sucursal_id(
        source_branch_name,
        session=session,
        source_family=GASCA_SOURCE_FAMILY,
    )


def resolve_trainingym_center_id(
    _source_center_name: object,
    *,
    session: Any,
) -> int | None:
    # Track no autoriza actualmente una source_family para Trainingym.
    # La sesión forma parte del contrato inyectable aunque no se consulta.
    del session
    return None
