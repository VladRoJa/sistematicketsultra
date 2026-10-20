"""Alcance y flujo legacy de la cuenta regional de Mantenimiento.

La excepción pertenece a la identidad auditada, no al rol MANTENIMIENTO.
La sucursal principal 100 es administrativa y NUNCA confiere cobertura.
"""
from __future__ import annotations

MAINTENANCE_LEAD_ID = 45
MAINTENANCE_LEAD_USERNAME = "MANTENIMIENTO"
MAINTENANCE_LEAD_BRANCH_IDS = frozenset({
    1, 2, 3, 4, 5, 6, 14, 15, 16, 17, 18, 20, 24, 26,
})


def is_regional_maintenance_lead(user) -> bool:
    if user is None:
        return False
    try:
        return (
            int(getattr(user, "id", -1)) == MAINTENANCE_LEAD_ID
            and str(getattr(user, "username", "") or "").strip().upper()
            == MAINTENANCE_LEAD_USERNAME
            and str(getattr(user, "rol", "") or "").strip().upper()
            == "MANTENIMIENTO"
            and int(getattr(user, "department_id", -1)) == 1
        )
    except (ValueError, TypeError):
        return False


def regional_maintenance_lead_branches(user) -> tuple[int, ...]:
    """Solo membresías reales en usuario_sucursal Y la allowlist aprobada."""
    if not is_regional_maintenance_lead(user):
        return ()
    allowed = set()
    for raw in getattr(user, "sucursales_ids", None) or []:
        try:
            branch_id = int(raw)
        except (ValueError, TypeError):
            continue
        if branch_id in MAINTENANCE_LEAD_BRANCH_IDS:
            allowed.add(branch_id)
    return tuple(sorted(allowed))


def regional_maintenance_lead_owns_ticket(user, ticket) -> bool:
    if not is_regional_maintenance_lead(user) or ticket is None:
        return False
    try:
        if int(getattr(ticket, "departamento_id", -1)) != 1:
            return False
        destination = (
            getattr(ticket, "sucursal_id_destino", None)
            or getattr(ticket, "sucursal_id", None)
        )
        return int(destination) in regional_maintenance_lead_branches(user)
    except (ValueError, TypeError):
        return False


def can_regional_maintenance_lead_request_legacy_closure(user, ticket) -> bool:
    """Solo cierre propio no delegado; jamás sustituir revisión de técnicos."""
    return bool(
        regional_maintenance_lead_owns_ticket(user, ticket)
        and not str(getattr(ticket, "asignado_a", "") or "").strip()
        and not str(getattr(ticket, "tipo_atencion", "") or "").strip()
    )
