#backend\app\models\warehouse.py


from app.extensions import db
from datetime import datetime
from sqlalchemy import UniqueConstraint, Index
from sqlalchemy.orm import relationship

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