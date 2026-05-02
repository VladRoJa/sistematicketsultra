#backend\app\models\warehouse.py


from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint, Index
from sqlalchemy.orm import relationship

def _utc_now():
    return datetime.now(timezone.utc)

class WarehouseSourceORM(db.Model):
    __tablename__ = 'warehouse_sources'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), nullable=False, unique=True)
    label = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, default=True)

class WarehouseFamilyORM(db.Model):
    __tablename__ = 'warehouse_families'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), nullable=False, unique=True)
    label = db.Column(db.String(150), nullable=False)
    active = db.Column(db.Boolean, default=True)

class WarehouseOperationalRoleORM(db.Model):
    __tablename__ = 'warehouse_operational_roles'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), nullable=False, unique=True)
    label = db.Column(db.String(150), nullable=False)
    active = db.Column(db.Boolean, default=True)

class WarehouseReportTypeORM(db.Model):
    __tablename__ = 'warehouse_report_types'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), nullable=False, unique=True)
    label = db.Column(db.String(150), nullable=False)
    
    family_id = db.Column(db.Integer, db.ForeignKey('warehouse_families.id'), nullable=False)
    default_source_id = db.Column(db.Integer, db.ForeignKey('warehouse_sources.id'), nullable=True)
    default_operational_role_id = db.Column(db.Integer, db.ForeignKey('warehouse_operational_roles.id'), nullable=True)
    default_period_type = db.Column(db.String(20), nullable=True)
    
    active = db.Column(db.Boolean, default=True)
    
    # Relaciones para facilitar serialize
    family = db.relationship('WarehouseFamilyORM')
    default_source = db.relationship('WarehouseSourceORM')
    default_operational_role = db.relationship('WarehouseOperationalRoleORM')

class WarehouseUploadORM(db.Model):
    __tablename__ = 'warehouse_uploads'

    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.Text, nullable=False)
    file_size_bytes = db.Column(db.BigInteger, nullable=False)
    file_hash_sha256 = db.Column(db.String(64), nullable=False)
    mime_type = db.Column(db.String(100), nullable=True)
    extension = db.Column(db.String(10), nullable=False)
    
    source_id = db.Column(db.Integer, db.ForeignKey('warehouse_sources.id'), nullable=False)
    family_id = db.Column(db.Integer, db.ForeignKey('warehouse_families.id'), nullable=False)
    operational_role_id = db.Column(db.Integer, db.ForeignKey('warehouse_operational_roles.id'), nullable=False)
    report_type_id = db.Column(db.Integer, db.ForeignKey('warehouse_report_types.id'), nullable=False)
    
    period_type = db.Column(db.String(20), nullable=False) # 'diario' | 'rango'
    cutoff_date = db.Column(db.Date, nullable=True)
    date_from = db.Column(db.Date, nullable=True)
    date_to = db.Column(db.Date, nullable=True)
    
    status = db.Column(db.String(20), default='ACTIVE') # ACTIVE | ARCHIVED
    notes = db.Column(db.Text, nullable=True)
    
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.now())
    updated_at = db.Column(db.DateTime(timezone=True), default=db.func.now(), onupdate=db.func.now())
    
    # Indexes
    __table_args__ = (
        db.Index('idx_warehouse_uploads_source_id', 'source_id'),
        db.Index('idx_warehouse_uploads_report_type_id', 'report_type_id'),
        db.Index('idx_warehouse_uploads_created_at', 'created_at'),
    )

    # Relaciones
    source = db.relationship('WarehouseSourceORM')
    family = db.relationship('WarehouseFamilyORM')
    operational_role = db.relationship('WarehouseOperationalRoleORM')
    report_type = db.relationship('WarehouseReportTypeORM')
    uploader = db.relationship('UserORM')

class WarehouseOperatorORM(db.Model):
    __tablename__ = 'warehouse_operators'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    can_upload = db.Column(db.Boolean, default=True)
    can_view = db.Column(db.Boolean, default=True)
    can_archive = db.Column(db.Boolean, default=False)
    added_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.now())
    
    user = db.relationship('UserORM', foreign_keys=[user_id])
    added_by_user = db.relationship('UserORM', foreign_keys=[added_by_user_id])

class WarehouseAuditLogORM(db.Model):
    __tablename__ = 'warehouse_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    upload_id = db.Column(db.Integer, db.ForeignKey('warehouse_uploads.id'), nullable=True)
    action = db.Column(db.String(30), nullable=False) # UPLOAD, DOWNLOAD, ARCHIVE
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    details = db.Column(db.JSON, nullable=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.now())
    
    upload = db.relationship('WarehouseUploadORM')
    performer = db.relationship('UserORM')




class KpiDesempenoSnapshotORM(db.Model):
    __tablename__ = "kpi_desempeno_snapshots"

    id = db.Column(db.Integer, primary_key=True)

    warehouse_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id"),
        nullable=False,
        unique=True,
    )

    report_type_key = db.Column(db.String(100), nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.String(50), nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)

    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    warehouse_upload = db.relationship("WarehouseUploadORM")

    rows = db.relationship(
        "KpiDesempenoSnapshotRowORM",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_kpi_desempeno_snapshots_business_date", "business_date"),
        Index("ix_kpi_desempeno_snapshots_is_canonical", "is_canonical"),
    )


class KpiDesempenoSnapshotRowORM(db.Model):
    __tablename__ = "kpi_desempeno_snapshot_rows"

    id = db.Column(db.Integer, primary_key=True)

    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("kpi_desempeno_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )

    row_index = db.Column(db.Integer, nullable=False)
    sucursal = db.Column(db.String(255), nullable=False)

    socios_activos_inicio_mes = db.Column(db.Integer, nullable=False)
    clientes_nuevo_real = db.Column(db.Integer, nullable=False)
    reactivaciones = db.Column(db.Integer, nullable=False)
    renovaciones = db.Column(db.Integer, nullable=False)
    bajas = db.Column(db.Integer, nullable=False)
    socios_activos_del_mes = db.Column(db.Integer, nullable=False)
    meta_socios_activos_del_mes = db.Column(db.Integer, nullable=False)
    alcance_meta = db.Column(db.Numeric(12, 2), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    snapshot = db.relationship(
        "KpiDesempenoSnapshotORM",
        back_populates="rows",
    )

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "sucursal",
            name="uq_kpi_desempeno_snapshot_rows_snapshot_id_sucursal",
        ),
        Index("ix_kpi_desempeno_snapshot_rows_snapshot_id", "snapshot_id"),
    )
    
class KpiVentasNuevosSociosSnapshotORM(db.Model):
    __tablename__ = "kpi_ventas_nuevos_socios_snapshots"

    id = db.Column(db.Integer, primary_key=True)

    warehouse_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id"),
        nullable=False,
        unique=True,
    )

    report_type_key = db.Column(db.String(100), nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.String(50), nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)

    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    warehouse_upload = db.relationship("WarehouseUploadORM")

    rows = db.relationship(
        "KpiVentasNuevosSociosSnapshotRowORM",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "ix_kpi_ventas_nuevos_socios_snapshots_business_date",
            "business_date",
        ),
        Index(
            "ix_kpi_ventas_nuevos_socios_snapshots_is_canonical",
            "is_canonical",
        ),
    )


class KpiVentasNuevosSociosSnapshotRowORM(db.Model):
    __tablename__ = "kpi_ventas_nuevos_socios_snapshot_rows"

    id = db.Column(db.Integer, primary_key=True)

    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("kpi_ventas_nuevos_socios_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )

    row_index = db.Column(db.Integer, nullable=False)
    sucursal = db.Column(db.String(255), nullable=False)

    numero_cnm_meta = db.Column(db.Integer, nullable=False)
    ingreso_por_cnm_meta = db.Column(db.Numeric(12, 2), nullable=False)
    clientes_nuevos_real = db.Column(db.Integer, nullable=False)
    ingreso_clientes_nuevos_real = db.Column(db.Numeric(12, 2), nullable=False)
    cnreal_menos_meta_cnm = db.Column(db.Integer, nullable=False)
    porcentaje_meta = db.Column(db.Numeric(12, 2), nullable=False)
    cnreal_menos_meta_cnm_alt = db.Column(db.Numeric(12, 2), nullable=False)
    porcentaje_meta_alt = db.Column(db.Numeric(12, 2), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    snapshot = db.relationship(
        "KpiVentasNuevosSociosSnapshotORM",
        back_populates="rows",
    )

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "sucursal",
            name="uq_kpi_ventas_nuevos_socios_snapshot_rows_snapshot_id_sucursal",
        ),
        Index(
            "ix_kpi_ventas_nuevos_socios_snapshot_rows_snapshot_id",
            "snapshot_id",
        ),
    )
    
    
class CorteCajaSnapshotORM(db.Model):
    __tablename__ = "corte_caja_snapshots"

    id = db.Column(db.Integer, primary_key=True)

    warehouse_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id"),
        nullable=False,
        unique=True,
    )

    report_type_key = db.Column(db.String(100), nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.String(50), nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)

    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    warehouse_upload = db.relationship("WarehouseUploadORM")

    rows = db.relationship(
        "CorteCajaSnapshotRowORM",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_corte_caja_snapshots_business_date", "business_date"),
        Index("ix_corte_caja_snapshots_is_canonical", "is_canonical"),
    )


class CorteCajaSnapshotRowORM(db.Model):
    __tablename__ = "corte_caja_snapshot_rows"

    id = db.Column(db.Integer, primary_key=True)

    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("corte_caja_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )

    row_index = db.Column(db.Integer, nullable=False)

    clave = db.Column(db.String(100), nullable=True)
    folio = db.Column(db.String(100), nullable=False)
    hora = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    importe = db.Column(db.Numeric(12, 2), nullable=False)
    pago = db.Column(db.String(50), nullable=True)
    renovacion = db.Column(db.String(50), nullable=True)
    operacion = db.Column(db.String(100), nullable=True)
    tipo_pago = db.Column(db.String(100), nullable=True)
    recepcion = db.Column(db.String(255), nullable=True)
    sucursal = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    snapshot = db.relationship(
        "CorteCajaSnapshotORM",
        back_populates="rows",
    )

    __table_args__ = (
        Index("ix_corte_caja_snapshot_rows_snapshot_id", "snapshot_id"),
    )
    
class CargosRecurrentesSnapshotORM(db.Model):
    __tablename__ = "cargos_recurrentes_snapshots"

    id = db.Column(db.Integer, primary_key=True)

    warehouse_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id"),
        nullable=False,
        unique=True,
    )

    report_type_key = db.Column(db.String(100), nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.String(50), nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)

    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    warehouse_upload = db.relationship("WarehouseUploadORM")

    rows = db.relationship(
        "CargosRecurrentesSnapshotRowORM",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_cargos_recurrentes_snapshots_business_date", "business_date"),
        Index("ix_cargos_recurrentes_snapshots_is_canonical", "is_canonical"),
    )


class CargosRecurrentesSnapshotRowORM(db.Model):
    __tablename__ = "cargos_recurrentes_snapshot_rows"

    id = db.Column(db.Integer, primary_key=True)

    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("cargos_recurrentes_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )

    row_index = db.Column(db.Integer, nullable=False)

    folio = db.Column(db.String(100), nullable=False)
    id_socio = db.Column(db.String(100), nullable=False)
    pin = db.Column(db.String(100), nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    sucursal = db.Column(db.String(255), nullable=False)
    fecha_inicio = db.Column(db.String(50), nullable=False)
    fecha_proximo_pago = db.Column(db.String(50), nullable=False)
    numero_intentos = db.Column(db.Integer, nullable=False)
    hd = db.Column(db.String(100), nullable=True)
    estatus = db.Column(db.String(100), nullable=False)
    importe = db.Column(db.Numeric(12, 2), nullable=False)
    meses_pendiente = db.Column(db.String(100), nullable=True)
    fecha_fin_contrato = db.Column(db.String(50), nullable=True)
    tipo_contrato = db.Column(db.String(100), nullable=True)
    contrato_ajuste = db.Column(db.String(100), nullable=True)
    acciones = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    snapshot = db.relationship(
        "CargosRecurrentesSnapshotORM",
        back_populates="rows",
    )

    __table_args__ = (
        Index("ix_cargos_recurrentes_snapshot_rows_snapshot_id", "snapshot_id"),
    )
    
    
    
class VentaTotalSnapshotORM(db.Model):
    __tablename__ = "venta_total_snapshots"

    id = db.Column(db.Integer, primary_key=True)

    warehouse_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id"),
        nullable=False,
        unique=True,
    )

    report_type_key = db.Column(db.String(100), nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.String(50), nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)

    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    warehouse_upload = db.relationship("WarehouseUploadORM")

    rows = db.relationship(
        "VentaTotalSnapshotRowORM",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_venta_total_snapshots_business_date", "business_date"),
        Index("ix_venta_total_snapshots_is_canonical", "is_canonical"),
    )


class VentaTotalSnapshotRowORM(db.Model):
    __tablename__ = "venta_total_snapshot_rows"

    id = db.Column(db.Integer, primary_key=True)

    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("venta_total_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )

    row_index = db.Column(db.Integer, nullable=False)

    fecha = db.Column(db.String(50), nullable=False)
    sucursal = db.Column(db.String(255), nullable=False)
    folio = db.Column(db.String(100), nullable=False)
    clave = db.Column(db.String(100), nullable=True)
    clave_producto = db.Column(db.String(100), nullable=True)
    descripcion = db.Column(db.String(255), nullable=False)
    cantidad = db.Column(db.Numeric(12, 2), nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    iva_importe = db.Column(db.Numeric(12, 2), nullable=False)
    iva_tasa = db.Column(db.Numeric(12, 2), nullable=False)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    forma_pago = db.Column(db.String(100), nullable=False)
    estatus = db.Column(db.String(100), nullable=False)
    motivo = db.Column(db.String(255), nullable=True)
    realizo_venta = db.Column(db.String(255), nullable=False)
    hora = db.Column(db.String(50), nullable=False)
    id_orden = db.Column(db.String(100), nullable=True)
    encuesta = db.Column(db.String(255), nullable=True)
    capturista = db.Column(db.String(255), nullable=True)
    pin = db.Column(db.String(100), nullable=True)
    socio = db.Column(db.String(255), nullable=True)
    nuevo = db.Column(db.String(100), nullable=True)
    tipo = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    snapshot = db.relationship(
        "VentaTotalSnapshotORM",
        back_populates="rows",
    )

    __table_args__ = (
        Index("ix_venta_total_snapshot_rows_snapshot_id", "snapshot_id"),
    )
    
class TrackMonthlyTargetORM(db.Model):
    __tablename__ = "track_monthly_targets"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    target_month = db.Column(db.Date, nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )

    m2_sin_circulaciones = db.Column(db.Numeric(12, 2), nullable=False)
    usuarios_inicio_mes = db.Column(db.Integer, nullable=False)
    proyeccion_usuarios_cierre_mes = db.Column(db.Integer, nullable=False)

    meta_faycgo_mes = db.Column(db.Numeric(14, 2), nullable=False)
    meta_clientes_nuevos_mes = db.Column(db.Integer, nullable=False)
    meta_reactivaciones_mes = db.Column(db.Integer, nullable=False)
    meta_bajas_mes = db.Column(db.Integer, nullable=False)
    meta_nuevos_domiciliados_mes = db.Column(db.Integer, nullable=False)
    meta_arpu_mes = db.Column(db.Numeric(14, 2), nullable=False)
    meta_venta_tienda_mes = db.Column(db.Numeric(14, 2), nullable=False)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text, nullable=True)
    
class TrackBranchCatalogORM(db.Model):
    __tablename__ = "track_branch_catalog"

    sucursal_canon = db.Column(db.Text, primary_key=True)
    track_label = db.Column(db.Text, nullable=False)
    display_order = db.Column(db.Integer, nullable=False)
    is_track_active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text, nullable=True)
    
class TrackBranchAliasORM(db.Model):
    __tablename__ = "track_branch_aliases"

    source_family = db.Column(db.Text, primary_key=True)
    raw_branch_name = db.Column(db.Text, primary_key=True)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text, nullable=True)
    
class TrackSourceDesempenoDailyORM(db.Model):
    __tablename__ = "track_source_desempeno_daily"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    usuarios_activos_actual = db.Column(db.Integer, nullable=False)
    reactivaciones_real_mtd = db.Column(db.Integer, nullable=False)
    bajas_reales_mtd = db.Column(db.Integer, nullable=False)
    source_snapshot_id = db.Column(db.BigInteger, nullable=False)
    source_report_type_key = db.Column(db.Text, nullable=False)
    
class ReporteDireccionSnapshotORM(db.Model):
    __tablename__ = "reporte_direccion_snapshots"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    warehouse_upload_id = db.Column(db.BigInteger, nullable=False)
    report_type_key = db.Column(db.Text, nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.Text, nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)
    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)


class ReporteDireccionSnapshotRowORM(db.Model):
    __tablename__ = "reporte_direccion_snapshot_rows"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    snapshot_id = db.Column(
        db.BigInteger,
        db.ForeignKey("reporte_direccion_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    sucursal = db.Column(db.Text, nullable=False)
    ingreso_acumulado_mes_en_curso = db.Column(db.Numeric(14, 2), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)
    
class TrackSourceIngresosDailyORM(db.Model):
    __tablename__ = "track_source_ingresos_daily"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )

    ingreso_real_base_mtd = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    ingreso_wellhub_mtd = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    ingreso_totalpass_mtd = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    ingreso_real_agregadora_mtd = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    ingreso_real_total_mtd = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    # compatibilidad transitoria
    ingreso_real_mtd = db.Column(db.Numeric(14, 2), nullable=False)
    
    # compatibilidad legacy mientras migramos mart y serializer
    source_snapshot_id = db.Column(db.BigInteger, nullable=False)
    source_report_type_key = db.Column(db.Text, nullable=False)

    source_snapshot_id_reporte_direccion = db.Column(db.BigInteger, nullable=True)
    source_snapshot_id_wellhub = db.Column(db.BigInteger, nullable=True)
    source_snapshot_id_totalpass = db.Column(db.BigInteger, nullable=True)
    source_business_date_agregadoras = db.Column(db.Date, nullable=True)
    source_report_type_key_reporte_direccion = db.Column(db.Text, nullable=True)
    source_report_type_key_wellhub = db.Column(db.Text, nullable=True)
    source_report_type_key_totalpass = db.Column(db.Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "business_date",
            "sucursal_canon",
            name="uq_track_source_ingresos_daily_business_date_branch",
        ),
    )
    
class TrackSourceAgregadorasDailyORM(db.Model):
    __tablename__ = "track_source_agregadoras_daily"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False, 
    )

    ingreso_wellhub_mtd = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    ingreso_totalpass_mtd = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    ingreso_agregadora_total_mtd = db.Column(
        db.Numeric(14, 2),
        nullable=False,
        default=0,
    )

    source_snapshot_id_wellhub = db.Column(db.BigInteger, nullable=True)
    source_snapshot_id_totalpass = db.Column(db.BigInteger, nullable=True)

    source_report_type_key_wellhub = db.Column(db.Text, nullable=True)
    source_report_type_key_totalpass = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "business_date",
            "sucursal_canon",
            name="uq_track_source_agregadoras_daily_business_date_branch",
        ),
        Index(
            "ix_track_source_agregadoras_daily_business_date",
            "business_date",
        ),
        Index(
            "ix_track_source_agregadoras_daily_business_date_sucursal",
            "business_date",
            "sucursal_canon",
        ),
    )

class TrackSourceNuevosDailyORM(db.Model):
    __tablename__ = "track_source_nuevos_daily"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    clientes_nuevos_real_mtd = db.Column(db.Integer, nullable=False)
    source_snapshot_id = db.Column(db.BigInteger, nullable=False)
    source_report_type_key = db.Column(db.Text, nullable=False)
    
class DomiciliadosTotalSnapshotORM(db.Model):
    __tablename__ = "domiciliados_total_snapshots"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    warehouse_upload_id = db.Column(db.BigInteger, nullable=False)
    report_type_key = db.Column(db.Text, nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.Text, nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)
    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)


class DomiciliadosTotalSnapshotRowORM(db.Model):
    __tablename__ = "domiciliados_total_snapshot_rows"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    snapshot_id = db.Column(
        db.BigInteger,
        db.ForeignKey("domiciliados_total_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_index = db.Column(db.Integer, nullable=False)
    sucursal = db.Column(db.Text, nullable=False)
    general = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)
    

class TrackSourceDomiciliadosEfectivosDailyORM(db.Model):
    __tablename__ = "track_source_domiciliados_efectivos_daily"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    nuevos_domiciliados_real_mtd = db.Column(db.Integer, nullable=False)
    source_snapshot_id = db.Column(db.BigInteger, nullable=False)
    source_report_type_key = db.Column(db.Text, nullable=False)
    
class TrackDailyMartORM(db.Model):
    __tablename__ = "track_daily_mart"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    track_date = db.Column(db.Date, nullable=False)
    generation_mode = db.Column(db.Text, nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )

    # F2 metas / base mensual
    target_month = db.Column(db.Date, nullable=False)
    m2_sin_circulaciones = db.Column(db.Numeric(12, 2), nullable=True)
    usuarios_inicio_mes = db.Column(db.Integer, nullable=True)
    proyeccion_usuarios_cierre_mes = db.Column(db.Integer, nullable=True)
    meta_faycgo_mes = db.Column(db.Numeric(14, 2), nullable=True)
    meta_clientes_nuevos_mes = db.Column(db.Integer, nullable=True)
    meta_reactivaciones_mes = db.Column(db.Integer, nullable=True)
    meta_bajas_mes = db.Column(db.Integer, nullable=True)
    meta_nuevos_domiciliados_mes = db.Column(db.Integer, nullable=True)
    meta_arpu_mes = db.Column(db.Numeric(14, 2), nullable=True)
    meta_venta_tienda_mes = db.Column(db.Numeric(14, 2), nullable=True)

    # F3 desempeño
    usuarios_activos_actual = db.Column(db.Integer, nullable=True)
    reactivaciones_real_mtd = db.Column(db.Integer, nullable=True)
    bajas_reales_mtd = db.Column(db.Integer, nullable=True)

    # F4 ingresos
    ingreso_real_base_mtd = db.Column(db.Numeric(14, 2), nullable=True)
    ingreso_real_agregadora_mtd = db.Column(db.Numeric(14, 2), nullable=True)
    ingreso_real_total_mtd = db.Column(db.Numeric(14, 2), nullable=True)

    # compatibilidad transitoria
    ingreso_real_mtd = db.Column(db.Numeric(14, 2), nullable=True)
    
    # F5 nuevos
    clientes_nuevos_real_mtd = db.Column(db.Integer, nullable=True)

    # F6 domiciliados efectivos
    nuevos_domiciliados_real_mtd = db.Column(db.Integer, nullable=True)

    # lineage mínimo
    source_snapshot_id_desempeno = db.Column(db.BigInteger, nullable=True)
    source_snapshot_id_ingresos = db.Column(db.BigInteger, nullable=True)
    source_business_date_agregadoras = db.Column(db.Date, nullable=True)
    source_snapshot_id_nuevos = db.Column(db.BigInteger, nullable=True)
    source_snapshot_id_domiciliados = db.Column(db.BigInteger, nullable=True)
    source_business_date_desempeno = db.Column(db.Date, nullable=True)
    source_business_date_ingresos = db.Column(db.Date, nullable=True)   
    source_business_date_nuevos = db.Column(db.Date, nullable=True)
    source_business_date_domiciliados = db.Column(db.Date, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.func.now(),
    )
    
class IngresosWellhubSnapshotORM(db.Model):
    __tablename__ = "ingresos_wellhub_snapshots"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    warehouse_upload_id = db.Column(db.BigInteger, nullable=False, unique=True)
    report_type_key = db.Column(db.Text, nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.Text, nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)
    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)


class IngresosWellhubSnapshotRowORM(db.Model):
    __tablename__ = "ingresos_wellhub_snapshot_rows"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    snapshot_id = db.Column(
        db.BigInteger,
        db.ForeignKey("ingresos_wellhub_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    raw_branch_name = db.Column(db.Text, nullable=False)
    visitor_name = db.Column(db.Text, nullable=True)
    wellhub_member_id = db.Column(db.Text, nullable=True)
    total_checkins_mtd = db.Column(db.Integer, nullable=True)
    pago_total_mtd = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_ingresos_wellhub_snapshot_rows_snapshot_id", "snapshot_id"),
        Index(
            "ix_ingresos_wellhub_snapshot_rows_snapshot_id_sucursal_canon",
            "snapshot_id",
            "sucursal_canon",
        ),
        UniqueConstraint(
            "snapshot_id",
            "sucursal_canon",
            "wellhub_member_id",
            name="uq_ingresos_wellhub_snapshot_rows_snapshot_branch_member",
        ),
    )


class IngresosTotalpassSnapshotORM(db.Model):
    __tablename__ = "ingresos_totalpass_snapshots"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    warehouse_upload_id = db.Column(db.BigInteger, nullable=False, unique=True)
    report_type_key = db.Column(db.Text, nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    snapshot_kind = db.Column(db.Text, nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)
    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)


class IngresosTotalpassSnapshotRowORM(db.Model):
    __tablename__ = "ingresos_totalpass_snapshot_rows"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    snapshot_id = db.Column(
        db.BigInteger,
        db.ForeignKey("ingresos_totalpass_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    raw_branch_name = db.Column(db.Text, nullable=False)
    monto_acumulado_mes = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    usage_count = db.Column(db.Integer, nullable=True)
    student_count = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_ingresos_totalpass_snapshot_rows_snapshot_id", "snapshot_id"),
        Index(
            "ix_ingresos_totalpass_snapshot_rows_snapshot_id_sucursal_canon",
            "snapshot_id",
            "sucursal_canon",
        ),
        UniqueConstraint(
            "snapshot_id",
            "sucursal_canon",
            name="uq_ingresos_totalpass_snapshot_rows_snapshot_branch",
        ),
    )
    
class TrackDailyVersionORM(db.Model):
    __tablename__ = "track_daily_versions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    track_date = db.Column(db.Date, nullable=False)

    version_type = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False)

    generated_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    started_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)

    is_current = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )

    replaces_version_id = db.Column(
        db.BigInteger,
        db.ForeignKey("track_daily_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    base_version_id = db.Column(
        db.BigInteger,
        db.ForeignKey("track_daily_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    requested_by = db.Column(db.Text, nullable=True)
    trigger_source = db.Column(db.Text, nullable=False)
    retry_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )