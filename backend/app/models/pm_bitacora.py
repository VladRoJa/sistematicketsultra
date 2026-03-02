# backend\app\models\pm_bitacora.py

from datetime import datetime, timezone
from app.extensions import db

class PmBitacoraORM(db.Model):
    __tablename__ = "pm_bitacoras"

    id = db.Column(db.Integer, primary_key=True)

    # Activo global (inventario_general)
    inventario_id = db.Column(
        db.Integer,
        db.ForeignKey("inventario_general.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Sucursal explícita para scope/filtros
    sucursal_id = db.Column(db.Integer, nullable=False, index=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    fecha = db.Column(db.Date, nullable=False, index=True)

    # "OK" | "FALLA" | "OBS"
    resultado = db.Column(db.String(20), nullable=False)

    notas = db.Column(db.Text, nullable=True)

    # Respuestas del móvil (JSON)
    checks = db.Column(db.JSON, nullable=False, default=dict)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )