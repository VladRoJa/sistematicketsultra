# C:\Users\Vladimir\Documents\Sistema tickets\app\models\__init__.py

from .database import get_db_connection
from .ticket_model import Ticket
from .user_model import User
from .sucursal_model import Sucursal

__all__ = [
    "get_db_connection",
    "Ticket",
    "User",
    "Sucursal",
    "create_ticket",
    "get_tickets",
    "update_ticket_status",
    "get_user_by_credentials",
]
