# -------------------------------------------------------------------------------
# MODELOS: Inicialización de Modelos del Sistema
# -------------------------------------------------------------------------------

from .ticket_model import Ticket
from .user_model import UserORM
from .sucursal_model import Sucursal
from .inventario import Producto, InventarioSucursal, MovimientoInventario, DetalleMovimiento
from .departamento_model import Departamento

# -------------------------------------------------------------------------------
# EXPORTACIONES: Control de qué modelos estarán disponibles al importar app.models
# -------------------------------------------------------------------------------
__all__ = [
    "Ticket",
    "UserORM",
    "Sucursal",
    "Producto",
    "InventarioSucursal",
    "MovimientoInventario",
    "DetalleMovimiento",
    "Departamento"
]
