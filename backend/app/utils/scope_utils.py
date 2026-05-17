# backend/app/utils/scope_utils.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


ROOT_BRANCH_ID = 1000
CORPORATE_BRANCH_ID = 100

ROOT_ADMIN_ROLES = {
    "ADMINISTRADOR",
    "SUPER_ADMIN",
    "ADMIN",
}

GLOBAL_READ_ROLES = {
    "LECTOR_GLOBAL",
}

REGIONAL_ROLES = {
    "GERENTE_REGIONAL",
}

CORPORATE_ROLES = {
    "EDITOR_CORPORATIVO",
}

ALL_GLOBAL_ROLES = ROOT_ADMIN_ROLES | GLOBAL_READ_ROLES | CORPORATE_ROLES


@dataclass(frozen=True)
class BranchScope:
    is_global: bool
    branch_ids: tuple[int, ...]
    reason: str

    def to_dict(self) -> dict:
        return {
            "is_global": self.is_global,
            "branch_ids": list(self.branch_ids),
            "reason": self.reason,
        }


def normalize_role(role: str | None) -> str:
    return (role or "").strip().upper()


def normalize_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_branch_ids(values: Iterable | None) -> tuple[int, ...]:
    normalized: set[int] = set()

    for value in values or []:
        branch_id = normalize_int(value)

        if branch_id is not None:
            normalized.add(branch_id)

    return tuple(sorted(normalized))


def is_root_admin(user) -> bool:
    role = normalize_role(getattr(user, "rol", None))
    branch_id = normalize_int(getattr(user, "sucursal_id", None))

    return role in ROOT_ADMIN_ROLES and branch_id == ROOT_BRANCH_ID


def is_global_role(user) -> bool:
    role = normalize_role(getattr(user, "rol", None))

    return role in ALL_GLOBAL_ROLES


def is_corporate_user(user) -> bool:
    branch_id = normalize_int(getattr(user, "sucursal_id", None))

    return branch_id == CORPORATE_BRANCH_ID


def get_user_assigned_branch_ids(user) -> tuple[int, ...]:
    return normalize_branch_ids(getattr(user, "sucursales_ids", None))


def get_user_primary_branch_id(user) -> int | None:
    return normalize_int(getattr(user, "sucursal_id", None))


def get_user_branch_scope(user, *, allow_global_roles: bool = True) -> BranchScope:
    if user is None:
        return BranchScope(
            is_global=False,
            branch_ids=(),
            reason="missing_user",
        )

    role = normalize_role(getattr(user, "rol", None))

    if allow_global_roles and role in ALL_GLOBAL_ROLES:
        return BranchScope(
            is_global=True,
            branch_ids=(),
            reason=f"global_role:{role}",
        )

    assigned_branch_ids = get_user_assigned_branch_ids(user)

    if assigned_branch_ids:
        return BranchScope(
            is_global=False,
            branch_ids=assigned_branch_ids,
            reason="assigned_branches",
        )

    primary_branch_id = get_user_primary_branch_id(user)

    if primary_branch_id is not None:
        return BranchScope(
            is_global=False,
            branch_ids=(primary_branch_id,),
            reason="primary_branch",
        )

    return BranchScope(
        is_global=False,
        branch_ids=(),
        reason="empty_scope",
    )


def can_access_branch(user, sucursal_id, *, allow_global_roles: bool = True) -> bool:
    target_branch_id = normalize_int(sucursal_id)

    if target_branch_id is None:
        return False

    scope = get_user_branch_scope(
        user,
        allow_global_roles=allow_global_roles,
    )

    if scope.is_global:
        return True

    return target_branch_id in scope.branch_ids


def require_branch_access(user, sucursal_id, *, allow_global_roles: bool = True):
    if can_access_branch(
        user,
        sucursal_id,
        allow_global_roles=allow_global_roles,
    ):
        return None

    return {
        "error": "No tienes acceso a esta sucursal.",
        "detail": {
            "sucursal_id": normalize_int(sucursal_id),
            "scope": get_user_branch_scope(
                user,
                allow_global_roles=allow_global_roles,
            ).to_dict(),
        },
    }