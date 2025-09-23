# backend\app\utils\ticket_filters.py
from sqlalchemy import or_, and_
from app.models import Ticket

GERENTE_ROLES = {
    "GERENTE", "GERENTE_SUCURSAL", "GERENTE_GENERAL", "GERENTE_DEPTO"
    # agrega aquí todas las variantes reales que tengas en tu BD
}

ADMIN_ROLES = {
    "ADMINISTRADOR", "SUPER_ADMIN", "EDITOR_CORPORATIVO", "LECTOR_GLOBAL"
    # si quieres que LECTOR_GLOBAL vea TODO, agrégalo aquí
}

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

def filtrar_tickets_por_usuario(user):
    q = Ticket.query

    rol = (user.rol or "").upper().strip()
    suc = user.sucursal_id
    depto = user.department_id

    # 1) Admins
    if rol in ADMIN_ROLES or suc == 1000:
        print(f"[PERM] {user.username} rol={rol} suc={suc} -> ALL")
        return q

    # 2) Gerentes: por SUCURSAL
    if rol in GERENTE_ROLES:
        if not suc:
            print(f"[PERM] {user.username} rol={rol} SIN sucursal -> 0")
            return q.filter(False)
        print(f"[PERM] {user.username} rol={rol} suc={suc} -> SOLO SUCURSAL")
        return _filtro_solo_sucursal(q, suc)

    # 3) Jefaturas / encargados con department_id: por DEPARTAMENTO (todas las sucursales)
    if depto:
        try:
            depto_int = int(depto)
        except Exception:
            print(f"[PERM] {user.username} depto inválido={depto} -> 0")
            return q.filter(False)
        print(f"[PERM] {user.username} depto={depto_int} -> SOLO DEPARTAMENTO (todas las sucursales)")
        return q.filter(Ticket.departamento_id == depto_int)

    # 4) Operativos: por SUCURSAL
    if suc:
        print(f"[PERM] {user.username} rol={rol} suc={suc} -> SOLO SUCURSAL")
        return _filtro_solo_sucursal(q, suc)

    # 5) Fallback
    print(f"[PERM] {user.username} sin reglas -> 0")
    return q.filter(False)