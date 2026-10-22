"""Historial inmutable de correcciones del código interno de inventario."""
from datetime import datetime, timezone
from app.extensions import db


class InventarioCodigoCorreccionORM(db.Model):
    __tablename__ = "inventario_codigo_correcciones"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    inventario_id = db.Column(
        db.Integer,
        db.ForeignKey("inventario_general.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_usuario_id = db.Column(db.Integer, nullable=False)
    codigo_anterior = db.Column(db.String(50), nullable=False)
    codigo_nuevo = db.Column(db.String(50), nullable=False)
    motivo = db.Column(db.Text, nullable=False)
    ocurrido_en_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )

    __table_args__ = (
        db.Index(
            "ix_inv_codigo_correcciones_inventario",
            "inventario_id", "ocurrido_en_utc",
        ),
    )
