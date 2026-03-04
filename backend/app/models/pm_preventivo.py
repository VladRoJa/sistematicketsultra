# backend\app\models\pm_preventivo.py

from datetime import datetime, timezone
from app.extensions import db


class PmPreventivoConfigORM(db.Model):
    __tablename__ = "pm_preventivo_config"

    id = db.Column(db.Integer, primary_key=True)

    inventario_id = db.Column(
        db.Integer,
        db.ForeignKey("inventario_general.id", ondelete="CASCADE"),
        nullable=False,
    )

    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="CASCADE"),
        nullable=False,
    )

    frecuencia_dias = db.Column(db.Integer, nullable=False)

    activo = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("inventario_id", "sucursal_id", name="uq_pm_config_equipo"),
        db.CheckConstraint("frecuencia_dias > 0", name="ck_pm_config_frecuencia_positiva"),
    )

    def __repr__(self):
        return f"<PmPreventivoConfig inv={self.inventario_id} suc={self.sucursal_id} freq={self.frecuencia_dias}d>"
