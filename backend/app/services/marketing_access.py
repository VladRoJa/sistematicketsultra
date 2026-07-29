from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.utils.scope_utils import (
    ROOT_ADMIN_ROLES,
    get_user_assigned_branch_ids,
    get_user_branch_scope,
    get_user_primary_branch_id,
    normalize_branch_ids,
    normalize_role,
)


MARKETING_READ_ROLES = frozenset(
    {
        *ROOT_ADMIN_ROLES,
        "LECTOR_GLOBAL",
        "EDITOR_CORPORATIVO",
        "GERENTE",
        "GERENTE_REGIONAL",
        "SISTEMAS",
        "GERENCIA DEPORTIVA",
        "MARKETING",
        "TIENDA",
    }
)

MARKETING_INPUT_EDIT_ROLES = frozenset(
    {
        *ROOT_ADMIN_ROLES,
        "EDITOR_CORPORATIVO",
        "MARKETING",
    }
)


class MarketingAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class MarketingAccess:
    type: str
    is_global: bool
    branch_ids: tuple[int, ...]
    role: str
    can_edit_inputs: bool
    fallback_used: bool = False

    def visible_branch_ids(
        self,
        available_branch_ids: Iterable[int],
    ) -> tuple[int, ...]:
        available = normalize_branch_ids(available_branch_ids)
        if self.is_global:
            return available

        allowed = set(self.branch_ids)
        return tuple(
            branch_id
            for branch_id in available
            if branch_id in allowed
        )

    def to_scope_dict(
        self,
        available_branch_ids: Iterable[int],
    ) -> dict[str, object]:
        return {
            "type": self.type,
            "branch_ids": list(
                self.visible_branch_ids(
                    available_branch_ids
                )
            ),
        }


def resolve_marketing_access(user) -> MarketingAccess:
    if user is None:
        raise MarketingAuthorizationError(
            "Usuario no encontrado."
        )

    role = normalize_role(getattr(user, "rol", None))
    if role not in MARKETING_READ_ROLES:
        raise MarketingAuthorizationError(
            "No autorizado para consultar Marketing y Conversión."
        )

    can_edit_inputs = role in MARKETING_INPUT_EDIT_ROLES

    if role == "GERENTE":
        primary_branch_id = get_user_primary_branch_id(user)
        if primary_branch_id is None:
            raise MarketingAuthorizationError(
                "El gerente no tiene una sucursal primaria válida."
            )
        return MarketingAccess(
            type="PRIMARY_BRANCH",
            is_global=False,
            branch_ids=(primary_branch_id,),
            role=role,
            can_edit_inputs=can_edit_inputs,
        )

    if role == "GERENTE_REGIONAL":
        assigned_branch_ids = get_user_assigned_branch_ids(user)
        if assigned_branch_ids:
            return MarketingAccess(
                type="ASSIGNED_BRANCHES",
                is_global=False,
                branch_ids=assigned_branch_ids,
                role=role,
                can_edit_inputs=can_edit_inputs,
            )

        primary_branch_id = get_user_primary_branch_id(user)
        if primary_branch_id is None:
            raise MarketingAuthorizationError(
                "El gerente regional no tiene sucursales autorizadas."
            )
        return MarketingAccess(
            type="PRIMARY_BRANCH",
            is_global=False,
            branch_ids=(primary_branch_id,),
            role=role,
            can_edit_inputs=can_edit_inputs,
            fallback_used=True,
        )

    shared_scope = get_user_branch_scope(user)
    if shared_scope.is_global:
        return MarketingAccess(
            type="GLOBAL",
            is_global=True,
            branch_ids=(),
            role=role,
            can_edit_inputs=can_edit_inputs,
        )

    if not shared_scope.branch_ids:
        raise MarketingAuthorizationError(
            "El usuario no tiene sucursales autorizadas."
        )

    return MarketingAccess(
        type=(
            "ASSIGNED_BRANCHES"
            if shared_scope.reason == "assigned_branches"
            else "PRIMARY_BRANCH"
        ),
        is_global=False,
        branch_ids=shared_scope.branch_ids,
        role=role,
        can_edit_inputs=can_edit_inputs,
    )
