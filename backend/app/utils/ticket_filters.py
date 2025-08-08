# app/utils/ticket_filters.py

from app.models.ticket_model import Ticket
from sqlalchemy import or_

def filtrar_tickets_por_usuario(user, query=None):
    """
    Devuelve un query filtrado de tickets según los privilegios del usuario:
    - Recepción/Gerente: ve solo los tickets que ha creado (por username)
    - Jefe de departamento: ve tickets de su departamento y los que él ha creado
    - Admin: ve todo
    """
    if query is None:
        query = Ticket.query

    if hasattr(user, 'sucursal_id') and 1 <= user.sucursal_id <= 22:
        # Recepcionistas/gerentes de sucursal: solo sus tickets
        query = query.filter_by(username=user.username)

    elif hasattr(user, 'sucursal_id') and user.sucursal_id == 100:
        if not hasattr(user, 'department_id') or user.department_id is None:
            raise Exception("Supervisor sin departamento asignado")
        # Jefe de departamento: tickets de su depto o hechos por él
        query = query.filter(
            or_(
                Ticket.departamento_id == user.department_id,
                Ticket.username == user.username
            )
        )

    elif hasattr(user, 'sucursal_id') and user.sucursal_id == 1000:
        # Admin/Corporativo: sin filtro, ve todo
        pass

    else:
        raise Exception("Tipo de usuario no reconocido o sin permisos")

    return query
