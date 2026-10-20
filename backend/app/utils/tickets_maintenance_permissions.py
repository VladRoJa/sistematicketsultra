"""Autorización explícita de coordinación para Tickets V1 de Mantenimiento.

No sustituye PM execution, filtros por sucursal ni las validaciones por ticket.
Una autorización de coordinación NO concede capacidad de cierre ni de bitácora.
"""

from __future__ import annotations

from sqlalchemy import func, or_

from app.utils.pm_permissions import can_pm_view, normalize_pm_role
from app.utils.maintenance_regional_lead import is_regional_maintenance_lead


COORDINATE_ACTION = "tickets.maintenance.coordinate"
ASSIGNED_ONLY_ACTION = "tickets.maintenance.read_assigned_only"
ADMIN_ROLES = frozenset({"ADMINISTRADOR", "SUPER_ADMIN", "ADMIN"})
ASSIGNED_ONLY_ELIGIBLE_ROLES = frozenset({
    "SR_MANTENIMIENTO",
    "AUX_MANTENIMIENTO",
    "MANTENIMIENTO",
    "TECNICO",
})


def _has_active_user_grant(user, action_key: str) -> bool:
    """Consulta un allow individual vigente; nunca infiere autoridad del rol."""

    user_id = getattr(user, "id", None)
    if user_id is None:
        return False

    from app.models.permissions import PermissionActionORM, PermissionGrantORM

    rows = (
        PermissionGrantORM.query
        .join(PermissionGrantORM.action)
        .filter(
            PermissionActionORM.full_key == action_key,
            PermissionActionORM.is_active.is_(True),
            PermissionGrantORM.principal_type == "user",
            PermissionGrantORM.principal_user_id == user_id,
            # La capacidad se asigna globalmente, pero el endpoint siempre
            # intersecta el alcance operativo con usuario_sucursal.
            PermissionGrantORM.scope_type == "global",
            PermissionGrantORM.is_active.is_(True),
            PermissionGrantORM.deleted_at.is_(None),
            or_(
                PermissionGrantORM.starts_at.is_(None),
                PermissionGrantORM.starts_at <= func.now(),
            ),
            or_(
                PermissionGrantORM.expires_at.is_(None),
                PermissionGrantORM.expires_at > func.now(),
            ),
        )
        .with_entities(PermissionGrantORM.effect)
        .all()
    )
    return _effects_allow([row[0] for row in rows])


def _effects_allow(effects: list[str]) -> bool:
    """Un deny explícito activo prevalece sobre cualquier allow duplicado."""

    return "deny" not in effects and "allow" in effects


def has_maintenance_coordination_permission(user) -> bool:
    """Permiso para coordinar, NO para ejecutar o cerrar tickets.

    El alcance por sucursal y el estado del ticket deben verificarse
    por separado en cada endpoint de escritura.
    """

    if user is None:
        return False

    role = normalize_pm_role(getattr(user, "rol", None))
    if role in ADMIN_ROLES:
        return True

    # El jefe regional ejecuta y solicita cierre legacy, sin coordinación
    # ni selección de técnicos aunque existiera un grant incidental.
    if is_regional_maintenance_lead(user):
        return False

    # Los perfiles que ejecutan tickets asignados no deben convertirse en
    # coordinación por un grant incidental. Preservar otros roles legacy.
    if role in {"SR_MANTENIMIENTO", "AUX_MANTENIMIENTO", "TECNICO"}:
        return False

    return bool(
        can_pm_view(user)
        and _has_active_user_grant(user, COORDINATE_ACTION)
    )


def has_assigned_only_maintenance_scope(user) -> bool:
    """Opt-in individual: ver solo tickets de Mantenimiento asignados.

    No restringir a todo SR_MANTENIMIENTO por defecto: la activación del
    usuario debe ocurrir DESPUÉS de habilitar las asignaciones en V1.
    """

    if user is None:
        return False

    role = normalize_pm_role(getattr(user, "rol", None))
    if role not in ASSIGNED_ONLY_ELIGIBLE_ROLES:
        return False

    return _has_active_user_grant(user, ASSIGNED_ONLY_ACTION)
