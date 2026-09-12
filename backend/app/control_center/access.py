from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import or_

from app.extensions import db
from app.models.suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
)
from app.models.sucursal_model import Sucursal
from app.utils.scope_utils import (
    get_user_assigned_branch_ids,
    get_user_primary_branch_id,
    normalize_role,
)


ControlScopeType = Literal["GLOBAL", "REGION", "BRANCH_POOL", "BRANCH"]

CONTROL_GLOBAL_ROLES = frozenset(
    {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "LECTOR_GLOBAL",
    }
)
CONTROL_REGIONAL_ROLE = "GERENTE_REGIONAL"
CONTROL_BRANCH_ROLE = "GERENTE"
CONTROL_ALLOWED_ROLES = frozenset(
    {
        *CONTROL_GLOBAL_ROLES,
        CONTROL_REGIONAL_ROLE,
        CONTROL_BRANCH_ROLE,
    }
)
CONTROL_DOMAINS = (
    "commercial",
    "conversion",
    "retention",
    "maintenance",
)


class ControlAuthorizationError(PermissionError):
    pass


class ControlValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ControlScope:
    type: ControlScopeType
    region_keys: tuple[str, ...] = ()
    branch_ids: tuple[int, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "region_keys": list(self.region_keys),
            "branch_ids": list(self.branch_ids),
        }


@dataclass(frozen=True)
class ControlAccess:
    role: str
    max_scope: ControlScopeType
    authorized_scope: ControlScope
    allowed_domains: tuple[str, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "max_scope": self.max_scope,
            "authorized_scope": self.authorized_scope.to_public_dict(),
            "allowed_domains": list(self.allowed_domains),
            "navigable_dimensions": _navigable_dimensions(self.max_scope),
        }


def _navigable_dimensions(scope_type: ControlScopeType) -> list[str]:
    if scope_type == "GLOBAL":
        return ["REGION", "BRANCH", "SOURCE"]
    if scope_type in {"REGION", "BRANCH_POOL"}:
        return ["BRANCH", "SOURCE"]
    return ["SOURCE"]


def _normalize_branch_ids(values: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sorted({int(value) for value in values if int(value) > 0}))


def _load_region_keys_by_branch(
    branch_ids: tuple[int, ...],
    *,
    as_of_date: date,
) -> dict[int, tuple[str, ...]]:
    if not branch_ids:
        return {}

    rows = (
        db.session.query(
            SuiteSucursalRegionAssignmentORM,
            SuiteRegionORM,
        )
        .join(
            SuiteRegionORM,
            SuiteRegionORM.id == SuiteSucursalRegionAssignmentORM.region_id,
        )
        .filter(
            SuiteSucursalRegionAssignmentORM.sucursal_id.in_(branch_ids),
            SuiteRegionORM.is_active.is_(True),
            or_(
                SuiteSucursalRegionAssignmentORM.valid_from.is_(None),
                SuiteSucursalRegionAssignmentORM.valid_from <= as_of_date,
            ),
            or_(
                SuiteSucursalRegionAssignmentORM.valid_to.is_(None),
                SuiteSucursalRegionAssignmentORM.valid_to >= as_of_date,
            ),
        )
        .all()
    )

    result: dict[int, set[str]] = {}

    for assignment, region in rows:
        branch_id = int(assignment.sucursal_id)
        region_key = str(region.region_key or "").strip()
        if not region_key:
            continue
        result.setdefault(branch_id, set()).add(region_key)

    return {
        branch_id: tuple(sorted(region_keys))
        for branch_id, region_keys in result.items()
    }


def _resolve_regional_authorized_scope(
    user: Any,
    *,
    as_of_date: date,
) -> ControlScope:
    branch_ids = get_user_assigned_branch_ids(user)

    if not branch_ids:
        primary_branch_id = get_user_primary_branch_id(user)
        if primary_branch_id is not None:
            branch_ids = (primary_branch_id,)

    branch_ids = _normalize_branch_ids(branch_ids)

    if not branch_ids:
        raise ControlAuthorizationError(
            "El gerente regional no tiene sucursales autorizadas."
        )

    regions_by_branch = _load_region_keys_by_branch(
        branch_ids,
        as_of_date=as_of_date,
    )

    all_region_keys = {
        region_key
        for values in regions_by_branch.values()
        for region_key in values
    }
    every_branch_has_one_region = all(
        len(regions_by_branch.get(branch_id, ())) == 1
        for branch_id in branch_ids
    )

    if every_branch_has_one_region and len(all_region_keys) == 1:
        return ControlScope(
            type="REGION",
            region_keys=tuple(sorted(all_region_keys)),
            branch_ids=branch_ids,
        )

    return ControlScope(
        type="BRANCH_POOL",
        region_keys=tuple(sorted(all_region_keys)),
        branch_ids=branch_ids,
    )


def resolve_control_access(
    user: Any,
    *,
    as_of_date: date,
) -> ControlAccess:
    if user is None:
        raise ControlAuthorizationError("Usuario no encontrado.")

    role = normalize_role(getattr(user, "rol", None))

    if role not in CONTROL_ALLOWED_ROLES:
        raise ControlAuthorizationError(
            "No autorizado para consultar el Centro de Control."
        )

    if role in CONTROL_GLOBAL_ROLES:
        scope = ControlScope(type="GLOBAL")
        return ControlAccess(
            role=role,
            max_scope="GLOBAL",
            authorized_scope=scope,
            allowed_domains=CONTROL_DOMAINS,
        )

    if role == CONTROL_REGIONAL_ROLE:
        scope = _resolve_regional_authorized_scope(
            user,
            as_of_date=as_of_date,
        )
        return ControlAccess(
            role=role,
            max_scope=scope.type,
            authorized_scope=scope,
            allowed_domains=CONTROL_DOMAINS,
        )

    primary_branch_id = get_user_primary_branch_id(user)
    if primary_branch_id is None:
        raise ControlAuthorizationError(
            "El gerente no tiene una sucursal primaria válida."
        )

    scope = ControlScope(
        type="BRANCH",
        branch_ids=(primary_branch_id,),
    )
    return ControlAccess(
        role=role,
        max_scope="BRANCH",
        authorized_scope=scope,
        allowed_domains=CONTROL_DOMAINS,
    )


def _load_region_scope(
    region_key: str,
    *,
    as_of_date: date,
) -> ControlScope:
    normalized_region_key = str(region_key or "").strip()
    if not normalized_region_key:
        raise ControlValidationError("region_key es requerido para scope REGION.")

    rows = (
        db.session.query(SuiteSucursalRegionAssignmentORM)
        .join(
            SuiteRegionORM,
            SuiteRegionORM.id == SuiteSucursalRegionAssignmentORM.region_id,
        )
        .filter(
            SuiteRegionORM.region_key == normalized_region_key,
            SuiteRegionORM.is_active.is_(True),
            or_(
                SuiteSucursalRegionAssignmentORM.valid_from.is_(None),
                SuiteSucursalRegionAssignmentORM.valid_from <= as_of_date,
            ),
            or_(
                SuiteSucursalRegionAssignmentORM.valid_to.is_(None),
                SuiteSucursalRegionAssignmentORM.valid_to >= as_of_date,
            ),
        )
        .all()
    )

    branch_ids = tuple(
        sorted({int(row.sucursal_id) for row in rows})
    )
    if not branch_ids:
        raise ControlValidationError("region_key no tiene sucursales vigentes.")

    return ControlScope(
        type="REGION",
        region_keys=(normalized_region_key,),
        branch_ids=branch_ids,
    )


def _load_branch_scope(branch_id: Any) -> ControlScope:
    try:
        normalized_branch_id = int(branch_id)
    except (TypeError, ValueError) as exc:
        raise ControlValidationError("branch_id inválido.") from exc

    if normalized_branch_id <= 0:
        raise ControlValidationError("branch_id inválido.")

    exists = (
        db.session.query(Sucursal.sucursal_id)
        .filter(Sucursal.sucursal_id == normalized_branch_id)
        .first()
    )
    if exists is None:
        raise ControlValidationError("branch_id no existe.")

    return ControlScope(
        type="BRANCH",
        branch_ids=(normalized_branch_id,),
    )


def resolve_effective_scope(
    access: ControlAccess,
    *,
    as_of_date: date,
    requested_scope_type: str | None = None,
    region_key: str | None = None,
    branch_id: Any = None,
) -> ControlScope:
    requested = str(requested_scope_type or "").strip().upper()

    if not requested:
        return access.authorized_scope

    if requested not in {"GLOBAL", "REGION", "BRANCH_POOL", "BRANCH"}:
        raise ControlValidationError("scope_type inválido.")

    authorized = access.authorized_scope

    if access.max_scope == "GLOBAL":
        if requested == "GLOBAL":
            return authorized
        if requested == "REGION":
            return _load_region_scope(region_key or "", as_of_date=as_of_date)
        if requested == "BRANCH":
            return _load_branch_scope(branch_id)
        raise ControlValidationError(
            "Un usuario global no solicita BRANCH_POOL directamente."
        )

    if requested == "GLOBAL":
        raise ControlAuthorizationError(
            "El alcance GLOBAL está fuera del universo autorizado."
        )

    if requested == "REGION":
        if authorized.type != "REGION":
            raise ControlAuthorizationError(
                "El alcance REGION está fuera del universo autorizado."
            )
        normalized_region_key = str(region_key or "").strip()
        if normalized_region_key not in set(authorized.region_keys):
            raise ControlAuthorizationError(
                "Región fuera del alcance autorizado."
            )
        return authorized

    if requested == "BRANCH_POOL":
        if authorized.type != "BRANCH_POOL":
            raise ControlAuthorizationError(
                "El alcance BRANCH_POOL está fuera del universo autorizado."
            )
        return authorized

    branch_scope = _load_branch_scope(branch_id)
    requested_branch_id = branch_scope.branch_ids[0]
    if requested_branch_id not in set(authorized.branch_ids):
        raise ControlAuthorizationError(
            "Sucursal fuera del alcance autorizado."
        )
    return branch_scope
