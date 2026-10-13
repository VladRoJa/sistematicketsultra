"""Permiso independiente para consultar Control de Automatizaciones M1-B.

No reutilizar el guard de Salud de Sistemas: la autorización debe ser explícita
para este módulo y se aplica siempre en el backend.
"""


def can_read_automation_control(user: object | None) -> bool:
    if user is None:
        return False

    username = str(getattr(user, "username", "") or "").strip().upper()
    role = str(getattr(user, "rol", "") or "").strip().upper()

    return username == "ADMICORP"


def can_read_automation_logs(user: object | None) -> bool:
    """Permiso de diagnóstico independiente; M1 solo ADMICORP."""
    if user is None:
        return False
    username = str(getattr(user, "username", "") or "").strip().upper()
    return username == "ADMICORP"
