# backend/app/utils/ticket_filters.py
from sqlalchemy import or_, and_, func
from app.models import Ticket

GERENTE_ROLES = {"GERENTE", "GERENTE_SUCURSAL", "GERENTE_GENERAL", "GERENTE_DEPTO"}

ADMIN_ROLES = {"ADMINISTRADOR", "SUPER_ADMIN", "EDITOR_CORPORATIVO", "LECTOR_GLOBAL"}

TECH_ROLES = {"TECNICO", "SOPORTE", "SOPORTE_SISTEMAS","SR_MANTENIMIENTO"}


def _condicion_creador(user):
    username = (getattr(user, "username", None) or "").strip()

    if not username:
        return None

    return func.lower(Ticket.username) == username.lower()


def _filtrar_scope_o_creador(query, user, *scope_conditions):
    conditions = [condition for condition in scope_conditions if condition is not None]

    creator_condition = _condicion_creador(user)
    if creator_condition is not None:
        conditions.append(creator_condition)

    if not conditions:
        return query.filter(False)

    return query.filter(or_(*conditions))


def _condicion_solo_sucursal(sucursal_id: int):
    return or_(
        Ticket.sucursal_id_destino == int(sucursal_id),
        and_(
            Ticket.sucursal_id_destino.is_(None),
            Ticket.sucursal_id == int(sucursal_id)
        )
    )


def _condicion_multiples_sucursales(sucursales_ids: list[int]):
    ids = [int(x) for x in (sucursales_ids or [])]

    if not ids:
        return None

    return or_(
        Ticket.sucursal_id_destino.in_(ids),
        and_(
            Ticket.sucursal_id_destino.is_(None),
            Ticket.sucursal_id.in_(ids)
        )
    )

def filtrar_tickets_por_usuario(user):
    q = Ticket.query

    rol = (user.rol or "").upper().strip()
    suc = user.sucursal_id
    depto = user.department_id

    # Scope asignado por tabla usuario_sucursal (si existe en el modelo)
    scope = list(getattr(user, "sucursales_ids", None) or [])

    # 1) Admins por rol (ALL)
    if rol in ADMIN_ROLES:
        return q

    # 2) Gerente regional: SIEMPRE por scope (aunque suc=1000)
    if rol == "GERENTE_REGIONAL":
        if not scope:
            return _filtrar_scope_o_creador(q, user)
        return _filtrar_scope_o_creador(
            q,
            user,
            _condicion_multiples_sucursales(scope),
        )

    # 3) sucursal_id == 1000 SOLO otorga ALL si el rol realmente es admin/super_admin
    if suc == 1000 and rol in {"ADMINISTRADOR", "SUPER_ADMIN"}:
        return q

    # 4) Técnicos/Soporte con department_id:
    #    - base: SOLO su departamento
    #    - si hay scope: SOLO esas sucursales dentro del depto
    if depto and rol in TECH_ROLES:
        try:
            depto_int = int(depto)
        except Exception:
            return _filtrar_scope_o_creador(q, user)

        if scope:
            return _filtrar_scope_o_creador(
                q,
                user,
                and_(
                    Ticket.departamento_id == depto_int,
                    _condicion_multiples_sucursales(scope),
                ),
            )

        return _filtrar_scope_o_creador(
            q,
            user,
            Ticket.departamento_id == depto_int,
        )

    # 5) Gerentes: por SUCURSAL (1)
    if rol in GERENTE_ROLES:
        if not suc:
            return _filtrar_scope_o_creador(q, user)
        return _filtrar_scope_o_creador(
            q,
            user,
            _condicion_solo_sucursal(suc),
        )

    # 6) Jefaturas / encargados con department_id: por DEPARTAMENTO (todas las sucursales)
    if depto:
        try:
            depto_int = int(depto)
        except Exception:
            return _filtrar_scope_o_creador(q, user)
        return _filtrar_scope_o_creador(
            q,
            user,
            Ticket.departamento_id == depto_int,
        )

    # 7) Operativos: por SUCURSAL
    if suc:
        return _filtrar_scope_o_creador(
            q,
            user,
            _condicion_solo_sucursal(suc),
        )

    # 8) Fallback
    return _filtrar_scope_o_creador(q, user)
