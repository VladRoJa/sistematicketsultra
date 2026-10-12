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
    """BI y configuración del rollout: administración, sin cuenta piloto."""
    return (
        user is not None
        and _normalize(getattr(user, "rol", None))
        in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}
        and _normalize(getattr(user, "username", None)) != "ADMICORP"
    )
