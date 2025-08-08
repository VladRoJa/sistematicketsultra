# app\models\inventario.py

from datetime import datetime
from app. extensions import db
from app. utils.datetime_utils import format_datetime
import pytz

tz = pytz.timezone('America/Tijuana')

# ──────────────────────────────────────────────────────────
# MODELO: INVENTARIO GENERAL
# ──────────────────────────────────────────────────────────

class InventarioGeneral(db.Model):
    __tablename__ = 'inventario_general'

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)                
    nombre = db.Column(db.String(255), nullable=False)           
    descripcion = db.Column(db.Text)
    marca = db.Column(db.String(100))
    proveedor = db.Column(db.String(255))
    categoria = db.Column(db.String(100))
    unidad_medida = db.Column(db.String(50))
    codigo_interno = db.Column(db.String(50))                 
    no_equipo = db.Column(db.String(50))                   
    gasto_mes = db.Column(db.Integer)                              
    pedido_mes = db.Column(db.Integer)                       
    semana_pedido = db.Column(db.String(20))                      
    fecha_inventario = db.Column(db.Date)  
    gasto_sem = db.Column(db.Integer)       
    gasto_mes = db.Column(db.Integer)       
    pedido_mes = db.Column(db.Integer)      
    semana_pedido = db.Column(db.String(20)) 
    fecha_inventario = db.Column(db.Date)
    grupo_muscular = db.Column(db.String(100))
                       



    def __repr__(self):
        return f"<InventarioGeneral {self.tipo} {self.nombre}>"



# ──────────────────────────────────────────────────────────
# MODELO: INVENTARIO POR SUCURSAL
# ──────────────────────────────────────────────────────────

class InventarioSucursal(db.Model):
    __tablename__ = 'inventario_sucursal'

    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventario_general.id'), nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)
    stock = db.Column(db.Integer, default=0)

    inventario = db.relationship('InventarioGeneral', backref='inventarios_sucursal')

    def __repr__(self):
        return f"<InventarioSucursal Inventario {self.inventario_id} Stock {self.stock}>"

# ──────────────────────────────────────────────────────────
# MODELO: MOVIMIENTO DE INVENTARIO
# ──────────────────────────────────────────────────────────

class MovimientoInventario(db.Model):
    __tablename__ = 'movimientos_inventario'

    id = db.Column(db.Integer, primary_key=True)
    tipo_movimiento = db.Column(db.Enum('entrada', 'salida', name='tipo_movimiento_enum'), nullable=False)
    fecha = db.Column(db.DateTime, default=lambda: datetime.now(tz))
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)
    observaciones = db.Column(db.Text)

    detalles = db.relationship('DetalleMovimiento', back_populates='movimiento', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<MovimientoInventario {self.tipo_movimiento} {self.fecha}>"


# ──────────────────────────────────────────────────────────
# MODELO: DETALLE DE MOVIMIENTO
# ──────────────────────────────────────────────────────────

class DetalleMovimiento(db.Model):
    __tablename__ = 'detalle_movimiento'

    id = db.Column(db.Integer, primary_key=True)
    movimiento_id = db.Column(db.Integer, db.ForeignKey('movimientos_inventario.id'), nullable=False)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventario_general.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    unidad_medida = db.Column(db.String(50))

    movimiento = db.relationship('MovimientoInventario', back_populates='detalles')
    inventario = db.relationship('InventarioGeneral')

    def __repr__(self):
        return f"<DetalleMovimiento Inventario {self.inventario_id} Cantidad {self.cantidad}>"