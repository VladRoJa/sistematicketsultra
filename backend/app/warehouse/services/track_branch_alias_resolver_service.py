#   backend\app\warehouse\services\track_branch_alias_resolver_service.py


from __future__ import annotations

from typing import Any

from flask import g, has_request_context

from app.models.warehouse import TrackBranchAliasORM


_REQUEST_CACHE_KEY = "_track_branch_alias_cache"


class TrackBranchAliasResolverError(RuntimeError):
    """Error base del resolvedor de aliases del Track."""


def _ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise TrackBranchAliasResolverError(
            f"El campo {field_name!r} es obligatorio."
        )
    return normalized


def _get_request_cache() -> dict[tuple[str, str], str | None] | None:
    if not has_request_context():
        return None

    cache = getattr(g, _REQUEST_CACHE_KEY, None)

    if cache is None:
        cache = {}
        setattr(g, _REQUEST_CACHE_KEY, cache)

    return cache


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

    request_cache = _get_request_cache()
    cache_key = (
        normalized_source_family,
        normalized_raw_branch_name,
    )

    if request_cache is not None and cache_key in request_cache:
        return request_cache[cache_key]

    alias = TrackBranchAliasORM.query.filter_by(
        source_family=normalized_source_family,
        raw_branch_name=normalized_raw_branch_name,
        is_active=True,
    ).first()

    resolved_branch = alias.sucursal_canon if alias is not None else None

    if request_cache is not None:
        request_cache[cache_key] = resolved_branch

    return resolved_branch
