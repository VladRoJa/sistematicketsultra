# app\models\sucursal_model.py

from app. extensions import db

# ─────────────────────────────────────────────────────────────
# MODELO: SUCURSAL
# ─────────────────────────────────────────────────────────────

class SucursalOperationalStatus:
    PLANEADA = "PLANEADA"
    EN_APERTURA = "EN_APERTURA"
    ACTIVA = "ACTIVA"
    PAUSADA = "PAUSADA"
    CANCELADA = "CANCELADA"
    CERRADA = "CERRADA"

    ALL = (
        PLANEADA,
        EN_APERTURA,
        ACTIVA,
        PAUSADA,
        CANCELADA,
        CERRADA,
    )

class Sucursal(db.Model):
    __tablename__ = 'sucursales'

    sucursal_id = db.Column(db.Integer, primary_key=True)
    orden_apertura = db.Column(db.Integer, nullable=True)
    
    serie = db.Column(db.String(10), nullable=False)
    sucursal = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(100), nullable=False)
    operational_status = db.Column(
        db.String(32),
        nullable=False,
        default=SucursalOperationalStatus.ACTIVA,
        server_default=SucursalOperationalStatus.ACTIVA,
        index=True,
    )
    municipio = db.Column(db.String(100), nullable=False)
    direccion = db.Column(db.String(255), nullable=False)

    # Relaciones
    inventarios = db.relationship('InventarioSucursal', backref='sucursal', cascade='all, delete-orphan')
    movimientos = db.relationship('MovimientoInventario', backref='sucursal', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Sucursal {self.sucursal}>"
    
