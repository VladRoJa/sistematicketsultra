# app/models/__init__.py
from .database import get_db_connection
from .ticket_model import Ticket
from .user_model import User

__all__ = [
    "get_db_connection",
    "Ticket",
    "User",
    "create_ticket",
    "get_tickets",
    "update_ticket_status",
    "get_user_by_credentials",
]