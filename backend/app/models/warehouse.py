#backend\app\models\warehouse.py


from app.extensions import db
from datetime import datetime

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
