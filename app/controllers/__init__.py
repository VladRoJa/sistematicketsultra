# app/controllers/__init__.py
from .auth_controller import AuthController, auth_controller
from .ticket_controller import TicketController, ticket_controller

__all__ = [
    "AuthController",
    "auth_controller",
    "TicketController",
    "ticket_controller",
]