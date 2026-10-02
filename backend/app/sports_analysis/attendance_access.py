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
    get_user_assigned_branch_ids,
    get_user_primary_branch_id,
    normalize_role,
)


SPORTS_ANALYSIS_BETA_USERNAME = "ADMICORP"
SPORTS_ANALYSIS_GLOBAL_ROLES = frozenset({"GERENCIA DEPORTIVA"})
SPORTS_ANALYSIS_BRANCH_ROLE = "GERENTE"
SPORTS_ANALYSIS_REGIONAL_ROLE = "GERENTE_REGIONAL"
SPORTS_ANALYSIS_ALLOWED_ROLES = frozenset(
    {
        *SPORTS_ANALYSIS_GLOBAL_ROLES,
        SPORTS_ANALYSIS_BRANCH_ROLE,
        SPORTS_ANALYSIS_REGIONAL_ROLE,
    }
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

    username = str(
        user.username or ""
    ).strip().upper()
    role = normalize_role(user.rol)
    if (
        username != SPORTS_ANALYSIS_BETA_USERNAME
        and role not in SPORTS_ANALYSIS_ALLOWED_ROLES
    ):
        raise SportsAnalysisAuthorizationError(
            "Aforo y Asistencia no está habilitado "
            "para este perfil."
        )

    return user


def resolve_sports_analysis_scope(
    user: UserORM,
) -> SportsAnalysisScope:
    username = str(
        user.username or ""
    ).strip().upper()
    role = normalize_role(user.rol)
    if (
        username != SPORTS_ANALYSIS_BETA_USERNAME
        and role not in SPORTS_ANALYSIS_ALLOWED_ROLES
    ):
        raise SportsAnalysisAuthorizationError(
            "Aforo y Asistencia no está habilitado "
            "para este perfil."
        )

    all_branch_ids = tuple(
        item["id"]
        for item in list_sports_analysis_branches()
    )

    if (
        username == SPORTS_ANALYSIS_BETA_USERNAME
        or role in SPORTS_ANALYSIS_GLOBAL_ROLES
    ):
        return SportsAnalysisScope(
            role=role,
            is_global=True,
            allowed_branch_ids=all_branch_ids,
            fixed_branch_id=None,
        )

    available_branch_ids = set(all_branch_ids)

    if role == SPORTS_ANALYSIS_BRANCH_ROLE:
        primary_branch_id = get_user_primary_branch_id(user)
        if (
            primary_branch_id is None
            or primary_branch_id not in available_branch_ids
        ):
            raise SportsAnalysisAuthorizationError(
                "El gerente no tiene una sucursal "
                "operativa autorizada para Aforo y Asistencia."
            )

        return SportsAnalysisScope(
            role=role,
            is_global=False,
            allowed_branch_ids=(primary_branch_id,),
            fixed_branch_id=primary_branch_id,
        )

    assigned_branch_ids = tuple(
        branch_id
        for branch_id in get_user_assigned_branch_ids(user)
        if branch_id in available_branch_ids
    )
    if not assigned_branch_ids:
        primary_branch_id = get_user_primary_branch_id(user)
        if (
            primary_branch_id is not None
            and primary_branch_id in available_branch_ids
        ):
            assigned_branch_ids = (primary_branch_id,)

    if not assigned_branch_ids:
        raise SportsAnalysisAuthorizationError(
            "El gerente regional no tiene sucursales "
            "operativas autorizadas para Aforo y Asistencia."
        )

    return SportsAnalysisScope(
        role=role,
        is_global=False,
        allowed_branch_ids=assigned_branch_ids,
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
