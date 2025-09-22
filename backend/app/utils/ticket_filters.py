# app/utils/ticket_filters.py
from sqlalchemy import or_
from app.models.ticket_model import Ticket


def filtrar_tickets_por_usuario(user):
    """
    Devuelve un Query base con los tickets que el usuario puede ver.
    - ADMINISTRADOR / corporativo: ve todo.
    - GERENTE: ve lo suyo + lo de su sucursal + lo destinado a su sucursal.
    - Usuario normal: ve lo suyo + lo destinado a su sucursal.
    """
    q = Ticket.query

    # Admin corporativo (incluye sucursal 100/1000 si así lo manejas)
    rol = (user.rol or "").upper()
    es_admin_corp = (rol == "ADMINISTRADOR") or (rol == "LECTOR_GLOBAL") or (user.sucursal_id in (100, 1000))
    if es_admin_corp:
        return q

    # GERENTE: incluye destino a su sucursal
    if (user.rol or "").upper() == "GERENTE":
        return q.filter(
            or_(
                Ticket.username == user.username,            # lo que él creó
                Ticket.sucursal_id == user.sucursal_id,      # lo de su sucursal (si así ya lo contemplabas)
                Ticket.sucursal_id_destino == user.sucursal_id  # 🔴 NUEVO: lo destinado a su sucursal
            )
        )

    # Usuario regular: ve lo suyo + lo destinado a su sucursal
    return q.filter(
        or_(
            Ticket.username == user.username,
            Ticket.sucursal_id_destino == user.sucursal_id   # 🔴 NUEVO para usuarios no gerentes/admin
        )
    )
