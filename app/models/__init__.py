#app\models\__init__.py

# -------------------------------------------------------------------------------
# MODELOS: Inicialización de Modelos del Sistema
# -------------------------------------------------------------------------------

from .ticket_model import Ticket
from .user_model import UserORM
from .sucursal_model import Sucursal
from .inventario import InventarioGeneral, InventarioSucursal, MovimientoInventario, DetalleMovimiento
from .departamento_model import Departamento
from .formulario_ticket import FormularioTicket, CampoFormulario


# -------------------------------------------------------------------------------
# EXPORTACIONES: Control de qué modelos estarán disponibles al importar app.models
# -------------------------------------------------------------------------------
__all__ = [
    "Ticket",
    "UserORM",
    "Sucursal",
    "InventarioGeneral",
    "InventarioSucursal",
    "MovimientoInventario",
    "DetalleMovimiento",
    "Departamento",
    "FormularioTicket",
    "CampoFormulario",
]
