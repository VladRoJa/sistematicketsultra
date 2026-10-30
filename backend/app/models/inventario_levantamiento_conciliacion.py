"""E4: resoluciones de discrepancias y constancias de cierre, inmutables."""
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class InventarioLevantamientoResolucionORM(db.Model):
    __tablename__ = "inventario_levantamiento_resoluciones"
    id = db.Column(db.BigInteger, primary_key=True)
    levantamiento_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False)
    importacion_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False)
    caso = db.Column(db.String(80), nullable=False)
    accion = db.Column(db.String(24), nullable=False)
    solicitud_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_correccion_solicitudes.id", ondelete="RESTRICT"), nullable=True)
    inventario_id_resultante = db.Column(db.Integer, db.ForeignKey(
        "inventario_general.id", ondelete="RESTRICT"), nullable=True)
    movimiento_id = db.Column(db.Integer, db.ForeignKey(
        "movimientos_inventario.id", ondelete="RESTRICT"), nullable=True)
    motivo = db.Column(db.Text, nullable=False)
    idempotency_key = db.Column(UUID(as_uuid=True), nullable=False)
    actor_usuario_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="RESTRICT"), nullable=False)
    creado_en_utc = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.UniqueConstraint("actor_usuario_id", "idempotency_key",
                            name="uq_inv_e4_resolucion_idempotencia"),
        db.CheckConstraint("accion IN ('E2_APROBADA','REGISTRADO_OFICIAL','BAJA_PREVIA')",
                           name="ck_inv_e4_resolucion_accion"),
        db.CheckConstraint("char_length(btrim(motivo)) BETWEEN 20 AND 2000",
                           name="ck_inv_e4_resolucion_motivo"),
        db.Index("ix_inv_e4_resolucion_version_caso", "importacion_id", "caso", "id"),
    )


class InventarioLevantamientoCierreORM(db.Model):
    __tablename__ = "inventario_levantamiento_cierres"
    id = db.Column(db.BigInteger, primary_key=True)
    levantamiento_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False, unique=True)
    importacion_id = db.Column(db.BigInteger, db.ForeignKey(
        "inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False)
    actor_usuario_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="RESTRICT"), nullable=False)
    cerrado_en_utc = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    motivo = db.Column(db.Text, nullable=False)
    idempotency_key = db.Column(UUID(as_uuid=True), nullable=False)
    resumen_cierre = db.Column(JSONB, nullable=False)
    __table_args__ = (
        db.UniqueConstraint("actor_usuario_id", "idempotency_key",
                            name="uq_inv_e4_cierre_idempotencia"),
        db.CheckConstraint("char_length(btrim(motivo)) BETWEEN 20 AND 2000",
                           name="ck_inv_e4_cierre_motivo"),
    )
