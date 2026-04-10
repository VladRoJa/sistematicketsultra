#   backend\app\warehouse\services\track_branch_alias_resolver_service.py


from __future__ import annotations

from typing import Any

from app.models.warehouse import TrackBranchAliasORM


class TrackBranchAliasResolverError(RuntimeError):
    """Error base del resolvedor de aliases del Track."""


def _ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise TrackBranchAliasResolverError(
            f"El campo {field_name!r} es obligatorio."
        )
    return normalized


def resolve_track_branch_alias(
    *,
    source_family: Any,
    raw_branch_name: Any,
) -> str | None:
    normalized_source_family = _ensure_text(
        source_family,
        field_name="source_family",
    )
    normalized_raw_branch_name = _ensure_text(
        raw_branch_name,
        field_name="raw_branch_name",
    )

    alias = TrackBranchAliasORM.query.filter_by(
        source_family=normalized_source_family,
        raw_branch_name=normalized_raw_branch_name,
        is_active=True,
    ).first()

    if alias is None:
        return None

    return alias.sucursal_canon