# backend/app/utils/pm_permissions.py

from __future__ import annotations

from dataclasses import dataclass


PM_ADMIN_ROLES = {
    "ADMINISTRADOR",
    "SUPER_ADMIN",
    "ADMIN",
}

PM_VIEW_ROLES = PM_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
    "AUX_MANTENIMIENTO",
    "SISTEMAS",
    "TECNICO",
    "GERENTE",
    "GERENTE_REGIONAL",
    "LECTOR_GLOBAL",
}

PM_EXECUTE_ROLES = PM_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
    "AUX_MANTENIMIENTO",
    "SISTEMAS",
    "TECNICO",
}

PM_VALIDATE_ROLES = PM_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
}

PM_CONFIGURE_ROLES = PM_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
}


@dataclass(frozen=True)
class PmPermissionResult:
    allowed: bool
    action: str
    role: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "role": self.role,
            "reason": self.reason,
        }


def normalize_pm_role(role: str | None) -> str:
    return (role or "").strip().upper()


def get_user_role(user) -> str:
    return normalize_pm_role(getattr(user, "rol", None))


def _check_pm_role(user, allowed_roles: set[str], action: str) -> PmPermissionResult:
    role = get_user_role(user)

    if not role:
      return PmPermissionResult(
          allowed=False,
          action=action,
          role="",
          reason="missing_role",
      )

    if role in allowed_roles:
        return PmPermissionResult(
            allowed=True,
            action=action,
            role=role,
            reason="role_allowed",
        )

    return PmPermissionResult(
        allowed=False,
        action=action,
        role=role,
        reason="role_not_allowed",
    )


def can_pm_view(user) -> bool:
    return _check_pm_role(user, PM_VIEW_ROLES, "view").allowed


def can_pm_execute(user) -> bool:
    return _check_pm_role(user, PM_EXECUTE_ROLES, "execute").allowed


def can_pm_validate(user) -> bool:
    return _check_pm_role(user, PM_VALIDATE_ROLES, "validate").allowed


def can_pm_configure(user) -> bool:
    return _check_pm_role(user, PM_CONFIGURE_ROLES, "configure").allowed


def can_pm_admin(user) -> bool:
    return _check_pm_role(user, PM_ADMIN_ROLES, "admin").allowed


def require_pm_view(user):
    result = _check_pm_role(user, PM_VIEW_ROLES, "view")

    if result.allowed:
        return None

    return (
        {
            "error": "Forbidden",
            "detail": "No tienes permiso para consultar PM.",
            "permission": result.to_dict(),
        },
        403,
    )


def require_pm_execute(user):
    result = _check_pm_role(user, PM_EXECUTE_ROLES, "execute")

    if result.allowed:
        return None

    return (
        {
            "error": "Forbidden",
            "detail": "No tienes permiso para ejecutar bitácoras PM.",
            "permission": result.to_dict(),
        },
        403,
    )


def require_pm_validate(user):
    result = _check_pm_role(user, PM_VALIDATE_ROLES, "validate")

    if result.allowed:
        return None

    return (
        {
            "error": "Forbidden",
            "detail": "No tienes permiso para validar bitácoras PM.",
            "permission": result.to_dict(),
        },
        403,
    )


def require_pm_configure(user):
    result = _check_pm_role(user, PM_CONFIGURE_ROLES, "configure")

    if result.allowed:
        return None

    return (
        {
            "error": "Forbidden",
            "detail": "No tienes permiso para configurar programación PM.",
            "permission": result.to_dict(),
        },
        403,
    )


def require_pm_admin(user):
    result = _check_pm_role(user, PM_ADMIN_ROLES, "admin")

    if result.allowed:
        return None

    return (
        {
            "error": "Forbidden",
            "detail": "No tienes permiso de administración técnica PM.",
            "permission": result.to_dict(),
        },
        403,
    )