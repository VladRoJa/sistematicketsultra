# app\routes\__init__.py

# ------------------------------------------------------------------------------
# BLUEPRINTS: RUTAS REGISTRADAS
# ------------------------------------------------------------------------------

from .auth_routes import auth_bp
from .ticket_routes import ticket_bp
from .main_routes import main_bp


__all__ = [
    "auth_bp",
    "ticket_bp",
    "main_bp"
]

