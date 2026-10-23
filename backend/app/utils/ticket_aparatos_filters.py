"""Filtro SQL para incluir ticket principal y secundarios de un aparato.

Usar EXISTS, no JOIN: el ticket mantiene identidad única en listados,
historiales, reportes y paginaciones; los permisos se aplican aparte.
"""

from sqlalchemy import or_

from app.models.ticket_model import Ticket
from app.models.ticket_aparato import TicketAparatoORM


def ticket_relacionado_con_aparato(inventario_id):
    return or_(
        Ticket.aparato_id == inventario_id,
        Ticket.aparatos_asociados.any(
            TicketAparatoORM.inventario_id == inventario_id
        ),
    )


def ticket_relacionado_con_alguno(inventario_ids):
    return or_(
        Ticket.aparato_id.in_(inventario_ids),
        Ticket.aparatos_asociados.any(
            TicketAparatoORM.inventario_id.in_(inventario_ids)
        ),
    )
