# C:\Users\Vladimir\Documents\Sistema tickets\app\models\inventario.py

from datetime import datetime
from app.extensions import db
from app.utils.datetime_utils import format_datetime

# ──────────────────────────────────────────────────────────
# MODELO: PRODUCTO
# ──────────────────────────────────────────────────────────

class Producto(db.Model):
    __tablename__ = 'productos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False)
    descripcion = db.Column(db.Text)
    unidad_medida = db.Column(db.String(50))
    categoria = db.Column(db.String(100))
    subcategoria = db.Column(db.String(100))

    # Relaciones
    inventarios = db.relationship('InventarioSucursal', back_populates='producto', cascade='all, delete-orphan')
    detalles_movimiento = db.relationship('DetalleMovimiento', back_populates='producto', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Producto {self.nombre}>"


# ──────────────────────────────────────────────────────────
# MODELO: INVENTARIO POR SUCURSAL
# ──────────────────────────────────────────────────────────

class InventarioSucursal(db.Model):
    __tablename__ = 'inventario_sucursal'

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)
    stock = db.Column(db.Integer, default=0)

    # Relaciones
    producto = db.relationship('Producto', back_populates='inventarios')

    def __repr__(self):
        return f"<InventarioSucursal Producto {self.producto_id} Stock {self.stock}>"


# ──────────────────────────────────────────────────────────
# MODELO: MOVIMIENTO DE INVENTARIO
# ──────────────────────────────────────────────────────────

class MovimientoInventario(db.Model):
    __tablename__ = 'movimientos_inventario'

    id = db.Column(db.Integer, primary_key=True)
    tipo_movimiento = db.Column(db.Enum('entrada', 'salida', name='tipo movimiento_enum'), nullable=False)
    fecha = db.Column(db.DateTime, server_default=db.func.now())
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)
    observaciones = db.Column(db.Text)

    # Relaciones
    detalles = db.relationship('DetalleMovimiento', back_populates='movimiento', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<MovimientoInventario {self.tipo_movimiento} {format_datetime(self.fecha)}>"


# ──────────────────────────────────────────────────────────
# MODELO: DETALLE DE MOVIMIENTO
# ──────────────────────────────────────────────────────────

class DetalleMovimiento(db.Model):
    __tablename__ = 'detalle_movimiento'

    id = db.Column(db.Integer, primary_key=True)
    movimiento_id = db.Column(db.Integer, db.ForeignKey('movimientos_inventario.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    unidad_medida = db.Column(db.String(50))

    # Relaciones
    movimiento = db.relationship('MovimientoInventario', back_populates='detalles')
    producto = db.relationship('Producto', back_populates='detalles_movimiento')

    def __repr__(self):
        return f"<DetalleMovimiento Producto {self.producto_id} Cantidad {self.cantidad}>"
