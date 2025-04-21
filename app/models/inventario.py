# C:\Users\Vladimir\Documents\Sistema tickets\app\models\inventario.py


from app.extensions import db 


class Producto(db.Model):
    __tablename__ = 'productos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False)
    descripcion = db.Column(db.Text)
    unidad_medida = db.Column(db.String(50))
    categoria = db.Column(db.String(100))
    subcategoria = db.Column(db.String(100))

class InventarioSucursal(db.Model):
    __tablename__ = 'inventario_sucursal'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'))
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id_sucursal'))
    stock = db.Column(db.Integer, default=0)

class MovimientoInventario(db.Model):
    __tablename__ = 'movimientos_inventario'
    id = db.Column(db.Integer, primary_key=True)
    tipo_movimiento = db.Column(db.Enum('entrada', 'salida'), nullable=False)
    fecha = db.Column(db.DateTime, server_default=db.func.now())
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id_sucursal'))
    observaciones = db.Column(db.Text)

class DetalleMovimiento(db.Model):
    __tablename__ = 'detalle_movimiento'
    id = db.Column(db.Integer, primary_key=True)
    movimiento_id = db.Column(db.Integer, db.ForeignKey('movimientos_inventario.id'))
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'))
    cantidad = db.Column(db.Integer, nullable=False)
    unidad_medida = db.Column(db.String(50))
