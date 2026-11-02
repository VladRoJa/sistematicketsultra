"""Inventarios E4 Bloque 1: evidencia de corte, importaciones y filas (sin mutar V1)."""
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class InventarioLevantamientoORM(db.Model):
    __tablename__ = "inventario_levantamientos"
    id = db.Column(db.BigInteger, primary_key=True)
    cycle_key = db.Column(UUID(as_uuid=True), nullable=False, unique=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"), nullable=False)
    origen_corte = db.Column(db.String(24), nullable=False)
    modalidad = db.Column(db.String(16), nullable=False)
    responsable = db.Column(db.String(200), nullable=True)
    fecha_corte_local = db.Column(db.Date, nullable=True)
    creado_por_usuario_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    creado_en_utc = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    baseline_sha256 = db.Column(db.String(64), nullable=True)
    baseline_storage_key = db.Column(db.String(250), nullable=True)
    baseline_capturado_en_utc = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    baseline_resumen = db.Column(JSONB, nullable=False, default=dict)
    estado = db.Column(db.String(24), nullable=False, default="IN_PROGRESS")
    ultima_importacion_id = db.Column(db.BigInteger, nullable=True)

    __table_args__ = (
        db.CheckConstraint("origen_corte IN ('CSV_HISTORICO','DB_ACTUAL','INICIAL')", name="ck_inv_e4_origen"),
        db.CheckConstraint("modalidad IN ('VERIFICACION','INICIAL')", name="ck_inv_e4_modalidad"),
        db.CheckConstraint("estado IN ('PREPARATION','IN_PROGRESS','IN_REVIEW','CLOSED')", name="ck_inv_e4_estado"),
        db.Index("ix_inv_e4_levantamientos_sucursal_fecha", "sucursal_id", "creado_en_utc"),
    )


class InventarioLevantamientoReferenciaORM(db.Model):
    __tablename__ = "inventario_levantamiento_referencias"
    id = db.Column(db.BigInteger, primary_key=True)
    levantamiento_id = db.Column(db.BigInteger, db.ForeignKey("inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False)
    inventario_id_original = db.Column(db.Integer, nullable=False)
    codigo_interno_original = db.Column(db.String(100), nullable=True)
    stock_original = db.Column(db.Integer, nullable=False)
    datos_originales = db.Column(JSONB, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("levantamiento_id", "inventario_id_original", name="uq_inv_e4_ref_corte_id"),
        db.CheckConstraint("stock_original > 0", name="ck_inv_e4_ref_stock_positivo"),
        db.Index("ix_inv_e4_ref_inventario", "inventario_id_original"),
    )


class InventarioLevantamientoImportacionORM(db.Model):
    __tablename__ = "inventario_levantamiento_importaciones"
    id = db.Column(db.BigInteger, primary_key=True)
    levantamiento_id = db.Column(db.BigInteger, db.ForeignKey("inventario_levantamientos.id", ondelete="RESTRICT"), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    idempotency_key = db.Column(UUID(as_uuid=True), nullable=False)
    file_sha256 = db.Column(db.String(64), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(250), nullable=False)
    cargado_por_usuario_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    cargado_en_utc = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    resultado = db.Column(db.String(16), nullable=False)
    control = db.Column(JSONB, nullable=False, default=dict)
    resumen = db.Column(JSONB, nullable=False, default=dict)
    diagnosticos = db.Column(JSONB, nullable=False, default=list)

    __table_args__ = (
        db.UniqueConstraint("levantamiento_id", "version", name="uq_inv_e4_import_version"),
        db.UniqueConstraint("levantamiento_id", "idempotency_key", name="uq_inv_e4_import_idempotency"),
        db.UniqueConstraint("levantamiento_id", "file_sha256", name="uq_inv_e4_import_hash"),
        db.CheckConstraint("version >= 1", name="ck_inv_e4_import_version"),
        db.CheckConstraint("resultado IN ('VALIDATED','INCOMPLETE','INVALID')", name="ck_inv_e4_import_resultado"),
        db.Index("ix_inv_e4_import_levantamiento_fecha", "levantamiento_id", "cargado_en_utc"),
    )


class InventarioLevantamientoFilaORM(db.Model):
    __tablename__ = "inventario_levantamiento_filas"
    id = db.Column(db.BigInteger, primary_key=True)
    importacion_id = db.Column(db.BigInteger, db.ForeignKey("inventario_levantamiento_importaciones.id", ondelete="RESTRICT"), nullable=False)
    hoja = db.Column(db.String(12), nullable=False)
    fila_excel = db.Column(db.Integer, nullable=False)
    inventario_id_declarado = db.Column(db.Integer, nullable=True)
    codigo_declarado = db.Column(db.String(120), nullable=True)
    respuesta = db.Column(db.String(12), nullable=True)
    datos_crudos = db.Column(JSONB, nullable=False)
    diagnosticos = db.Column(JSONB, nullable=False, default=list)
    __table_args__ = (
        db.UniqueConstraint("importacion_id", "hoja", "fila_excel", name="uq_inv_e4_fila_ubicacion"),
        db.CheckConstraint("hoja IN ('APARATOS','HALLAZGOS')", name="ck_inv_e4_fila_hoja"),
        db.CheckConstraint("respuesta IS NULL OR respuesta IN ('SI','NO','SIN_REVISAR')", name="ck_inv_e4_fila_respuesta"),
    )
