# backend/app/utils/ticket_filters.py
from sqlalchemy import or_, and_
from app.models import Ticket

GERENTE_ROLES = {"GERENTE", "GERENTE_SUCURSAL", "GERENTE_GENERAL", "GERENTE_DEPTO"}

ADMIN_ROLES = {"ADMINISTRADOR", "SUPER_ADMIN", "EDITOR_CORPORATIVO", "LECTOR_GLOBAL"}

TECH_ROLES = {"TECNICO", "SOPORTE", "SOPORTE_SISTEMAS"}


def _filtro_solo_sucursal(query, sucursal_id: int):
    return query.filter(
        or_(
            Ticket.sucursal_id_destino == int(sucursal_id),
            and_(
                Ticket.sucursal_id_destino.is_(None),
                Ticket.sucursal_id == int(sucursal_id)
            )
        )
    )


def _filtro_multiples_sucursales(query, sucursales_ids: list[int]):
    """
    Mismo criterio que _filtro_solo_sucursal, pero para un set de sucursales.
    - Prioriza sucursal_id_destino IN (scope)
    - Si sucursal_id_destino es NULL, cae a Ticket.sucursal_id IN (scope)
    """
    ids = [int(x) for x in (sucursales_ids or [])]
    if not ids:
        return query.filter(False)

    return query.filter(
        or_(
            Ticket.sucursal_id_destino.in_(ids),
            and_(
                Ticket.sucursal_id_destino.is_(None),
                Ticket.sucursal_id.in_(ids)
            )
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
        print(f"[PERM] {user.username} rol={rol} suc={suc} -> ALL (ADMIN_ROLES)")
        return q

    # 2) Gerente regional: SIEMPRE por scope (aunque suc=1000)
    if rol == "GERENTE_REGIONAL":
        if not scope:
            print(f"[PERM] {user.username} rol={rol} SIN sucursales_ids -> 0")
            return q.filter(False)
        print(f"[PERM] {user.username} rol={rol} scope={scope} -> MULTI SUCURSAL")
        return _filtro_multiples_sucursales(q, scope)

    # 3) sucursal_id == 1000 SOLO otorga ALL si el rol realmente es admin/super_admin
    if suc == 1000 and rol in {"ADMINISTRADOR", "SUPER_ADMIN"}:
        print(f"[PERM] {user.username} rol={rol} suc={suc} -> ALL (suc=1000 admin)")
        return q

    # 4) Técnicos/Soporte con department_id:
    #    - base: SOLO su departamento
    #    - si hay scope: SOLO esas sucursales dentro del depto
    if depto and rol in TECH_ROLES:
        try:
            depto_int = int(depto)
        except Exception:
            print(f"[PERM] {user.username} rol={rol} depto inválido={depto} -> 0")
            return q.filter(False)

        base = q.filter(Ticket.departamento_id == depto_int)

        if scope:
            print(f"[PERM] {user.username} rol={rol} depto={depto_int} scope={scope} -> DEPTO + MULTI SUCURSAL")
            return _filtro_multiples_sucursales(base, scope)

        print(f"[PERM] {user.username} rol={rol} depto={depto_int} -> SOLO DEPARTAMENTO (sin scope)")
        return base

    # 5) Gerentes: por SUCURSAL (1)
    if rol in GERENTE_ROLES:
        if not suc:
            print(f"[PERM] {user.username} rol={rol} SIN sucursal -> 0")
            return q.filter(False)
        print(f"[PERM] {user.username} rol={rol} suc={suc} -> SOLO SUCURSAL")
        return _filtro_solo_sucursal(q, suc)

    # 6) Jefaturas / encargados con department_id: por DEPARTAMENTO (todas las sucursales)
    if depto:
        try:
            depto_int = int(depto)
        except Exception:
            print(f"[PERM] {user.username} depto inválido={depto} -> 0")
            return q.filter(False)
        print(f"[PERM] {user.username} depto={depto_int} -> SOLO DEPARTAMENTO (todas las sucursales)")
        return q.filter(Ticket.departamento_id == depto_int)

    # 7) Operativos: por SUCURSAL
    if suc:
        print(f"[PERM] {user.username} rol={rol} suc={suc} -> SOLO SUCURSAL")
        return _filtro_solo_sucursal(q, suc)

    # 8) Fallback
    print(f"[PERM] {user.username} sin reglas -> 0")
    return q.filter(False)