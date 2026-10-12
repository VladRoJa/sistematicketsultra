from __future__ import annotations


def _normalize(value: object) -> str:
    return str(value or "").strip().upper()


def has_system_daily_check_mvp_access(user) -> bool:
    """Permiso para CAPTURAR checklists diarios en la sucursal asignada."""
    return (
        user is not None
        and _normalize(getattr(user, "rol", None)) == "GERENTE"
    )


def has_system_daily_check_bi_access(user) -> bool:
    """Acceso a panel Salud de Sistemas: SISTEMAS o ADMICORP."""
    return user is not None and (
        _normalize(getattr(user, "rol", None)) == "SISTEMAS"
        or _normalize(getattr(user, "username", None)) == "ADMICORP"
    )


def has_system_daily_check_rollout_access(user) -> bool:
    """Sólo la cuenta ADMICORP administra las sucursales del checklist."""
    return (
        user is not None
        and _normalize(getattr(user, "username", None)) == "ADMICORP"
    )
