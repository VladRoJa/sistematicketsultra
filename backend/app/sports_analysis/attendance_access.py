from __future__ import annotations

from dataclasses import dataclass

from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.sucursal_model import (
    Sucursal,
    SucursalOperationalStatus,
)
from app.models.suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
)
from app.models.user_model import UserORM
from app.models.warehouse import TrackBranchCatalogORM
from app.utils.scope_utils import (
    normalize_branch_ids,
    normalize_role,
)


SPORTS_ANALYSIS_GLOBAL_ROLES = frozenset(
    {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "LECTOR_GLOBAL",
        "GERENCIA DEPORTIVA",
    }
)
SPORTS_ANALYSIS_ALLOWED_ROLES = (
    SPORTS_ANALYSIS_GLOBAL_ROLES
    | {"GERENTE", "GERENTE_REGIONAL"}
)


class SportsAnalysisAuthorizationError(
    PermissionError
):
    pass


@dataclass(frozen=True, slots=True)
class SportsAnalysisScope:
    role: str
    is_global: bool
    allowed_branch_ids: tuple[int, ...]
    fixed_branch_id: int | None


def get_current_sports_analysis_user() -> UserORM:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise SportsAnalysisAuthorizationError(
            "Sesión inválida."
        ) from exc

    user = db.session.get(UserORM, user_id)
    if user is None:
        raise SportsAnalysisAuthorizationError(
            "Usuario no encontrado."
        )
    return user


def resolve_sports_analysis_scope(
    user: UserORM,
) -> SportsAnalysisScope:
    role = normalize_role(user.rol)
    if role not in SPORTS_ANALYSIS_ALLOWED_ROLES:
        raise SportsAnalysisAuthorizationError(
            "No tienes acceso a Análisis Deportivo."
        )

    all_branch_ids = tuple(
        item["id"]
        for item in list_sports_analysis_branches()
    )
    all_branch_set = set(all_branch_ids)

    if role in SPORTS_ANALYSIS_GLOBAL_ROLES:
        return SportsAnalysisScope(
            role=role,
            is_global=True,
            allowed_branch_ids=all_branch_ids,
            fixed_branch_id=None,
        )

    if role == "GERENTE":
        try:
            branch_id = int(user.sucursal_id)
        except (TypeError, ValueError) as exc:
            raise SportsAnalysisAuthorizationError(
                "El gerente no tiene una "
                "sucursal válida."
            ) from exc

        if branch_id not in all_branch_set:
            raise SportsAnalysisAuthorizationError(
                "La sucursal del gerente no está "
                "habilitada para Análisis Deportivo."
            )

        return SportsAnalysisScope(
            role=role,
            is_global=False,
            allowed_branch_ids=(branch_id,),
            fixed_branch_id=branch_id,
        )

    assigned = normalize_branch_ids(
        user.sucursales_ids
    )
    if not assigned:
        try:
            assigned = (int(user.sucursal_id),)
        except (TypeError, ValueError) as exc:
            raise SportsAnalysisAuthorizationError(
                "El gerente regional no tiene "
                "sucursales autorizadas."
            ) from exc

    effective = tuple(
        branch_id
        for branch_id in assigned
        if branch_id in all_branch_set
    )
    if not effective:
        raise SportsAnalysisAuthorizationError(
            "El gerente regional no tiene "
            "sucursales activas para "
            "Análisis Deportivo."
        )

    return SportsAnalysisScope(
        role=role,
        is_global=False,
        allowed_branch_ids=effective,
        fixed_branch_id=None,
    )


def list_sports_analysis_branches() -> list[dict]:
    rows = (
        db.session.query(
            Sucursal.sucursal_id,
            Sucursal.sucursal,
            TrackBranchCatalogORM.track_label,
            TrackBranchCatalogORM.display_order,
            SuiteRegionORM.region_key,
            SuiteRegionORM.region_label,
        )
        .join(
            TrackBranchCatalogORM,
            TrackBranchCatalogORM.sucursal_id
            == Sucursal.sucursal_id,
        )
        .outerjoin(
            SuiteSucursalRegionAssignmentORM,
            (
                SuiteSucursalRegionAssignmentORM
                .sucursal_id
                == Sucursal.sucursal_id
            )
            & (
                SuiteSucursalRegionAssignmentORM
                .is_current.is_(True)
            ),
        )
        .outerjoin(
            SuiteRegionORM,
            (
                SuiteRegionORM.id
                == SuiteSucursalRegionAssignmentORM
                .region_id
            )
            & SuiteRegionORM.is_active.is_(True),
        )
        .filter(
            Sucursal.operational_status
            == SucursalOperationalStatus.ACTIVA,
            Sucursal.is_demo.is_(False),
            TrackBranchCatalogORM.is_track_active
            .is_(True),
            TrackBranchCatalogORM.sucursal_id
            .isnot(None),
        )
        .order_by(
            TrackBranchCatalogORM.display_order,
            Sucursal.sucursal,
        )
        .all()
    )

    result: dict[int, dict] = {}
    for (
        branch_id,
        branch_name,
        track_label,
        display_order,
        region_key,
        region_label,
    ) in rows:
        normalized_id = int(branch_id)
        item = result.setdefault(
            normalized_id,
            {
                "id": normalized_id,
                "name": branch_name,
                "track_label": track_label,
                "display_order": int(
                    display_order
                ),
                "region_key": region_key,
                "region_name": region_label,
            },
        )
        if (
            item["region_key"] is not None
            and item["region_key"] != region_key
        ):
            item["region_key"] = None
            item["region_name"] = None

    return list(result.values())


def scoped_branch_catalog(
    scope: SportsAnalysisScope,
) -> list[dict]:
    allowed = set(scope.allowed_branch_ids)
    return [
        item
        for item in list_sports_analysis_branches()
        if item["id"] in allowed
    ]
