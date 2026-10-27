"""Política E3 de autorizaciones: lectura estricta de DB, sin efectos.

No concede grants, no expone endpoints ni aplica propuestas.
El servicio E3 futuro debe invocar esto con datos de la solicitud leídos
dentro de su transacción y bajo bloqueo, nunca con sucursal/autor del cliente.
"""
from dataclasses import dataclass

from sqlalchemy import text

from app.extensions import db


_ACTION = "inventory.correction_approve"
_GLOBAL_ADMIN_ROLES = frozenset({"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"})
_SCOPED_APPROVER_ROLES = frozenset({
    "MANTENIMIENTO", "COORDINADOR_MANTENIMIENTO", "SISTEMAS",
})
# Ningún rol operativo hereda ámbito global del inventario V1.
_ROLE_COMPETENCE = {
    "MANTENIMIENTO": (1, "aparatos"),
    "COORDINADOR_MANTENIMIENTO": (1, "aparatos"),
    "SISTEMAS": (7, "dispositivos"),
}
_ASSET_CLASS_ALIASES = {
    "aparatos": frozenset({"aparato", "aparatos"}),
    "dispositivos": frozenset({"dispositivo", "dispositivos", "sistema", "sistemas"}),
}
_ALLOWED_TYPES = frozenset({
    "MASTER_FIELD", "QUANTITY_DIFFERENCE",
    "NOT_LOCATED", "UNREGISTERED_FIND",
})


@dataclass(frozen=True)
class InventoryCorrectionApprovalAccess:
    allowed: bool
    reason: str
    global_scope: bool = False


def normalizar_clase_inventario_e3(value):
    """Clase efectiva E3; sin inferirla de familia/categoría, fail closed."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    for class_name, aliases in _ASSET_CLASS_ALIASES.items():
        if normalized in aliases:
            return class_name
    return None


def aliases_clase_inventario_e3(class_name):
    return tuple(sorted(_ASSET_CLASS_ALIASES.get(class_name, ())))


def _positive_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _grant_covers_branch(grant, branch, department):
    """Una concesión no sustituye el scope de sucursales asignadas."""
    kind = str(grant["scope_type"] or "").lower()
    if kind == "global":
        return True
    if kind == "branch":
        return grant["scope_branch_id"] == branch
    if kind == "branch_list":
        raw = grant["scope_branch_ids"]
        return (
            isinstance(raw, list)
            and all(_positive_int(x) is not None for x in raw)
            and branch in raw
        )
    if kind == "department":
        return (
            _positive_int(grant["scope_department_id"]) is not None
            and department == grant["scope_department_id"]
        )
    # No interpretar grants 'module' o 'custom' como autorización crítica.
    return False


def resolver_acceso_autorizacion_e3(
    *, actor_usuario_id, solicitud_sucursal_id, solicitud_creador_id, tipo,
    clase_activo=None,
):
    """Decisión de elegibilidad; sin writes ni dependencia del JWT de rol.

    Se exige acción activa y grant explícito vigente para autorizar.
    Roles permitidos: administración (solo grant individual global),
    Mantenimiento (dept 1, aparatos) y Sistemas (dept 7, dispositivos),
    siempre sujetos a grant y usuario_sucursal asignada.
    Gerentes/regionales quedan fuera hasta el gate E5.
    """
    actor_id = _positive_int(actor_usuario_id)
    branch = _positive_int(solicitud_sucursal_id)
    creator = _positive_int(solicitud_creador_id)
    if not actor_id or not branch or not creator or tipo not in _ALLOWED_TYPES:
        return InventoryCorrectionApprovalAccess(False, "invalid_request")
    if actor_id == creator:
        return InventoryCorrectionApprovalAccess(False, "self_approval_forbidden")

    actor = db.session.execute(
        text("""
            SELECT id, rol, department_id
            FROM users WHERE id = :user_id
        """),
        {"user_id": actor_id},
    ).mappings().first()
    if not actor:
        return InventoryCorrectionApprovalAccess(False, "actor_not_found")

    role = str(actor["rol"] or "").strip().upper()
    if role not in _GLOBAL_ADMIN_ROLES | _SCOPED_APPROVER_ROLES:
        return InventoryCorrectionApprovalAccess(False, "role_not_enabled")
    if (role in _SCOPED_APPROVER_ROLES
            and actor["department_id"] != _ROLE_COMPETENCE[role][0]):
        return InventoryCorrectionApprovalAccess(False, "department_not_enabled")

    grants = db.session.execute(
        text("""
            SELECT g.principal_type, g.effect, g.scope_type,
                   g.scope_branch_id, g.scope_branch_ids,
                   g.scope_department_id
            FROM permission_grants g
            JOIN permission_actions a ON a.id = g.action_id
            JOIN permission_modules m ON m.id = a.module_id
            WHERE a.full_key = :action
              AND a.is_active IS TRUE
              AND m.key = 'inventory'
              AND m.is_active IS TRUE
              AND g.is_active IS TRUE
              AND g.deleted_at IS NULL
              AND (g.starts_at IS NULL OR g.starts_at <= now())
              AND (g.expires_at IS NULL OR g.expires_at > now())
              AND (
                    (g.principal_type = 'user' AND g.principal_user_id = :user_id)
                 OR (g.principal_type = 'role' AND
                     upper(btrim(g.principal_role_key)) = :role)
              )
        """),
        {"action": _ACTION, "user_id": actor_id, "role": role},
    ).mappings().all()

    # Un deny explícito relevante prima sobre cualquier allow, incluso global.
    if any(
        g["effect"] == "deny"
        and _grant_covers_branch(g, branch, actor["department_id"])
        for g in grants
    ):
        return InventoryCorrectionApprovalAccess(False, "explicit_deny")

    # El alcance corporativo necesita grant individual global explícito.
    # Un grant por rol ADMINISTRADOR no escala otras cuentas corporativas.
    if role in _GLOBAL_ADMIN_ROLES:
        if any(
            g["principal_type"] == "user"
            and g["scope_type"] == "global"
            and g["effect"] == "allow"
            for g in grants
        ):
            return InventoryCorrectionApprovalAccess(True, "explicit_global_grant", True)
        return InventoryCorrectionApprovalAccess(False, "no_explicit_global_grant")

    # Correcciones al maestro afectan múltiples sucursales: competencia corporativa.
    if tipo == "MASTER_FIELD":
        return InventoryCorrectionApprovalAccess(False, "global_master_requires_corporate")
    if normalizar_clase_inventario_e3(clase_activo) != _ROLE_COMPETENCE[role][1]:
        return InventoryCorrectionApprovalAccess(False, "asset_class_not_enabled")

    assigned = db.session.execute(
        text("""
            SELECT sucursal_id FROM usuario_sucursal
            WHERE user_id = :user_id
        """),
        {"user_id": actor_id},
    ).scalars().all()
    if branch not in assigned:
        return InventoryCorrectionApprovalAccess(False, "branch_not_assigned")

    matching = [
        g for g in grants
        if _grant_covers_branch(g, branch, actor["department_id"])
    ]
    if any(g["effect"] == "allow" for g in matching):
        return InventoryCorrectionApprovalAccess(True, "explicit_scoped_grant")
    return InventoryCorrectionApprovalAccess(False, "no_explicit_scoped_grant")


def alcance_revision_e3(actor_usuario_id):
    """Sucursales de revisión autorizadas en DB; sin JWT ni permisos E2.

    Se devuelven únicamente sucursales efectivas. Para administración se exige
    grant global personal; roles de mantenimiento intersecan usuario_sucursal.
    Los deny vigentes prevalecen, sin exponer sucursales ajenas al cliente.
    """
    actor_id = _positive_int(actor_usuario_id)
    if not actor_id:
        return None
    actor = db.session.execute(text(
        "SELECT id, rol, department_id FROM users WHERE id=:id"
    ), {"id": actor_id}).mappings().first()
    if actor is None:
        return None
    role = str(actor["rol"] or "").strip().upper()
    if role not in _GLOBAL_ADMIN_ROLES | _SCOPED_APPROVER_ROLES:
        return None
    if (role in _SCOPED_APPROVER_ROLES
            and actor["department_id"] != _ROLE_COMPETENCE[role][0]):
        return None
    grants = db.session.execute(text("""
        SELECT g.principal_type, g.effect, g.scope_type,
               g.scope_branch_id, g.scope_branch_ids, g.scope_department_id
        FROM permission_grants g
        JOIN permission_actions a ON a.id = g.action_id
        JOIN permission_modules m ON m.id = a.module_id
        WHERE a.full_key = :action AND a.is_active IS TRUE
          AND m.key = 'inventory' AND m.is_active IS TRUE
          AND g.is_active IS TRUE AND g.deleted_at IS NULL
          AND (g.starts_at IS NULL OR g.starts_at <= now())
          AND (g.expires_at IS NULL OR g.expires_at > now())
          AND ((g.principal_type = 'user' AND g.principal_user_id = :id)
               OR (g.principal_type = 'role'
                   AND upper(btrim(g.principal_role_key)) = :role))
    """), {"action": _ACTION, "id": actor_id, "role": role}).mappings().all()
    corporate = role in _GLOBAL_ADMIN_ROLES
    if corporate and not any(
        g["principal_type"] == "user"
        and g["scope_type"] == "global" and g["effect"] == "allow"
        for g in grants
    ):
        return None

    if corporate:
        candidate = db.session.execute(text(
            "SELECT sucursal_id FROM sucursales ORDER BY sucursal_id"
        )).scalars().all()
    else:
        candidate = db.session.execute(text(
            "SELECT sucursal_id FROM usuario_sucursal WHERE user_id=:id "
            "ORDER BY sucursal_id"
        ), {"id": actor_id}).scalars().all()

    permitted = []
    for raw in sorted(set(candidate)):
        branch = _positive_int(raw)
        if branch is None:
            continue
        if any(g["effect"] == "deny"
               and _grant_covers_branch(g, branch, actor["department_id"])
               for g in grants):
            continue
        if corporate or any(
            g["effect"] == "allow"
            and _grant_covers_branch(g, branch, actor["department_id"])
            for g in grants
        ):
            permitted.append(branch)
    if not permitted:
        return None
    return {"actor_id": actor_id, "sucursales": permitted,
            "corporativo": corporate,
            "clase_activo": None if corporate else _ROLE_COMPETENCE[role][1]}
