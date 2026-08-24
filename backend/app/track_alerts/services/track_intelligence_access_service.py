from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


TRACK_INTELLIGENCE_GLOBAL_ROLES = frozenset(
    {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "LECTOR_GLOBAL",
        "GERENTE_REGIONAL",
    }
)

TRACK_INTELLIGENCE_MANAGER_ROLE = "GERENTE"

TRACK_INTELLIGENCE_ALLOWED_ROLES = frozenset(
    {
        *TRACK_INTELLIGENCE_GLOBAL_ROLES,
        TRACK_INTELLIGENCE_MANAGER_ROLE,
    }
)


class TrackIntelligenceAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class TrackIntelligenceAccess:
    scope: Literal["global", "manager"]
    role: str
    is_global: bool
    primary_branch_id: int | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "is_global": self.is_global,
        }


def _normalize_role(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_branch_id(value: Any) -> int | None:
    try:
        branch_id = int(value)
    except (TypeError, ValueError):
        return None

    return branch_id if branch_id > 0 else None


def resolve_track_intelligence_access(
    user: Any,
) -> TrackIntelligenceAccess:
    if user is None:
        raise TrackIntelligenceAuthorizationError(
            "Usuario no encontrado."
        )

    role = _normalize_role(getattr(user, "rol", None))

    if role not in TRACK_INTELLIGENCE_ALLOWED_ROLES:
        raise TrackIntelligenceAuthorizationError(
            "No autorizado para consultar Inteligencia Operacional de Track."
        )

    if role in TRACK_INTELLIGENCE_GLOBAL_ROLES:
        return TrackIntelligenceAccess(
            scope="global",
            role=role,
            is_global=True,
            primary_branch_id=None,
        )

    primary_branch_id = _normalize_branch_id(
        getattr(user, "sucursal_id", None)
    )

    if primary_branch_id is None:
        raise TrackIntelligenceAuthorizationError(
            "El gerente no tiene una sucursal primaria válida."
        )

    return TrackIntelligenceAccess(
        scope="manager",
        role=role,
        is_global=False,
        primary_branch_id=primary_branch_id,
    )
