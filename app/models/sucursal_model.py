# C:\Users\Vladimir\Documents\Sistema tickets\app\models\sucursal_model.py

from app.extensions import db

# ─────────────────────────────────────────────────────────────
# MODELO: SUCURSAL
# ─────────────────────────────────────────────────────────────

class Sucursal(db.Model):
    __tablename__ = 'sucursales'

    sucursal_id = db.Column(db.Integer, primary_key=True)
    serie = db.Column(db.String(10), nullable=False)
    sucursal = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(100), nullable=False)
    municipio = db.Column(db.String(100), nullable=False)
    direccion = db.Column(db.String(255), nullable=False)

    # Relaciones
    inventarios = db.relationship('InventarioSucursal', backref='sucursal', cascade='all, delete-orphan')
    movimientos = db.relationship('MovimientoInventario', backref='sucursal', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Sucursal {self.sucursal}>"
    
