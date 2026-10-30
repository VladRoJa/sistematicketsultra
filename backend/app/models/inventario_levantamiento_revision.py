"""Inventarios E4: revisiones lógicas únicas y evidencia de cada entrega."""
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import JSONB
from app.extensions import db


def ahora_utc():
    return datetime.now(timezone.utc)


class InventarioLevantamientoRevisionORM(db.Model):
    __tablename__ = "inventario_levantamiento_revisiones"
    id = db.Column(db.BigInteger, primary_key=True)
    levantamiento_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False)
    logical_key = db.Column(db.String(160), nullable=False)
    tipo = db.Column(db.String(40), nullable=False)
    inventario_id = db.Column(db.Integer, nullable=True)
    codigo_observado = db.Column(db.String(120), nullable=True)
    campo = db.Column(db.String(64), nullable=True)
    estado = db.Column(db.String(30), nullable=False)
    motivo_bloqueo = db.Column(db.String(120), nullable=True)
    solicitud_e2_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_correccion_solicitudes.id", ondelete="RESTRICT"), nullable=True)
    primera_importacion_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False)
    ultima_importacion_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False)
    ultimo_valor = db.Column(JSONB, nullable=False)
    actor_creador_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="RESTRICT"), nullable=False)
    creado_en_utc = db.Column(db.DateTime(timezone=True), nullable=False, default=ahora_utc)
    actualizado_en_utc = db.Column(db.DateTime(timezone=True), nullable=False, default=ahora_utc)
    __table_args__ = (
        db.UniqueConstraint("levantamiento_id", "logical_key",
                            name="uq_inv_e4_revision_logica"),
        db.CheckConstraint(
            "estado IN ('BLOCKED','PENDING','AWAITING_E3','APPROVED','REJECTED','SUPERSEDED')",
            name="ck_inv_e4_revision_estado",
        ),
        db.Index("ix_inv_e4_revision_bandeja", "levantamiento_id", "estado", "id"),
        db.Index("ix_inv_e4_revision_e2", "solicitud_e2_id"),
    )


class InventarioLevantamientoRevisionEvidenciaORM(db.Model):
    __tablename__ = "inventario_levantamiento_revision_evidencias"
    id = db.Column(db.BigInteger, primary_key=True)
    revision_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamiento_revisiones.id", ondelete="RESTRICT"), nullable=False)
    importacion_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False)
    hoja = db.Column(db.String(12), nullable=True)
    fila_excel = db.Column(db.Integer, nullable=True)
    valor_observado = db.Column(JSONB, nullable=False)
    recibido_en_utc = db.Column(db.DateTime(timezone=True), nullable=False, default=ahora_utc)
    __table_args__ = (
        db.UniqueConstraint("revision_id", "importacion_id", "hoja", "fila_excel",
                            name="uq_inv_e4_revision_evidencia_fila"),
        db.Index("ix_inv_e4_revision_evidencia_version", "importacion_id"),
    )
