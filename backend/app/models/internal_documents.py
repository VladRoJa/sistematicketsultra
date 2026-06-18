# backend/app/models/internal_documents.py

from __future__ import annotations

from datetime import datetime, timezone

from app import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InternalDocumentStatus:
    DRAFT = "BORRADOR"
    PUBLISHED = "PUBLICADO"
    ARCHIVED = "ARCHIVADO"

    ALL = (DRAFT, PUBLISHED, ARCHIVED)


class InternalDocumentVisibilityMode:
    PRIVATE = "PRIVATE"
    CUSTOM = "CUSTOM"
    GLOBAL = "GLOBAL"

    ALL = (PRIVATE, CUSTOM, GLOBAL)


class InternalDocumentVisibilityType:
    GLOBAL = "GLOBAL"
    ROLE = "ROLE"
    DEPARTMENT = "DEPARTMENT"
    SUCURSAL = "SUCURSAL"
    USER = "USER"

    ALL = (GLOBAL, ROLE, DEPARTMENT, SUCURSAL, USER)

class InternalDocumentLinkEntityType:
    PROJECT = "PROJECT"
    OPENING = "OPENING"
    TASK = "TASK"
    SUCURSAL = "SUCURSAL"
    DEPARTMENT = "DEPARTMENT"
    GENERAL = "GENERAL"

    ALL = (
        PROJECT,
        OPENING,
        TASK,
        SUCURSAL,
        DEPARTMENT,
        GENERAL,
    )


class InternalDocumentLinkRole:
    PLANO = "PLANO"
    PERMISO = "PERMISO"
    CONTRATO = "CONTRATO"
    COTIZACION = "COTIZACION"
    CHECKLIST = "CHECKLIST"
    EVIDENCIA = "EVIDENCIA"
    MANUAL = "MANUAL"
    FINANCIERO = "FINANCIERO"
    CONSTRUCCION = "CONSTRUCCION"
    OPERACION = "OPERACION"
    OTRO = "OTRO"

    ALL = (
        PLANO,
        PERMISO,
        CONTRATO,
        COTIZACION,
        CHECKLIST,
        EVIDENCIA,
        MANUAL,
        FINANCIERO,
        CONSTRUCCION,
        OPERACION,
        OTRO,
    )

class InternalDocumentExternalProvider:
    GOOGLE_DRIVE = "GOOGLE_DRIVE"

    ALL = {
        GOOGLE_DRIVE,
    }


class InternalDocumentExternalResourceKind:
    VIDEO = "VIDEO"
    FOLDER = "FOLDER"
    LINK = "LINK"

    ALL = {
        VIDEO,
        FOLDER,
        LINK,
    }

class InternalDocumentAuditAction:
    DOCUMENT_CREATED = "DOCUMENT_CREATED"
    DOCUMENT_METADATA_UPDATED = "DOCUMENT_METADATA_UPDATED"
    DOCUMENT_PUBLISHED = "DOCUMENT_PUBLISHED"
    DOCUMENT_ARCHIVED = "DOCUMENT_ARCHIVED"
    DOCUMENT_VERSION_CREATED = "DOCUMENT_VERSION_CREATED"
    DOCUMENT_VERSION_REPLACED = "DOCUMENT_VERSION_REPLACED"
    DOCUMENT_VISIBILITY_UPDATED = "DOCUMENT_VISIBILITY_UPDATED"
    DOCUMENT_SENSITIVITY_UPDATED = "DOCUMENT_SENSITIVITY_UPDATED"
    DOCUMENT_OWNER_UPDATED = "DOCUMENT_OWNER_UPDATED"
    DOCUMENT_LINK_CREATED = "DOCUMENT_LINK_CREATED"
    DOCUMENT_LINK_UPDATED = "DOCUMENT_LINK_UPDATED"
    DOCUMENT_LINK_DEACTIVATED = "DOCUMENT_LINK_DEACTIVATED"
    EXTERNAL_RESOURCE_CREATED = "EXTERNAL_RESOURCE_CREATED"
    EXTERNAL_RESOURCE_UPDATED = "EXTERNAL_RESOURCE_UPDATED"
    EXTERNAL_RESOURCE_DEACTIVATED = "EXTERNAL_RESOURCE_DEACTIVATED"

    ALL = (
        DOCUMENT_CREATED,
        DOCUMENT_METADATA_UPDATED,
        DOCUMENT_PUBLISHED,
        DOCUMENT_ARCHIVED,
        DOCUMENT_VERSION_CREATED,
        DOCUMENT_VERSION_REPLACED,
        DOCUMENT_VISIBILITY_UPDATED,
        DOCUMENT_SENSITIVITY_UPDATED,
        DOCUMENT_OWNER_UPDATED,
        DOCUMENT_LINK_CREATED,
        DOCUMENT_LINK_UPDATED,
        DOCUMENT_LINK_DEACTIVATED,
        EXTERNAL_RESOURCE_CREATED,
        EXTERNAL_RESOURCE_UPDATED,
        EXTERNAL_RESOURCE_DEACTIVATED
    )


class InternalDocumentCategoryORM(db.Model):
    __tablename__ = "internal_document_categories"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    documents = db.relationship(
        "InternalDocumentORM",
        back_populates="category",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<InternalDocumentCategory key={self.key!r} name={self.name!r}>"


class InternalDocumentORM(db.Model):
    __tablename__ = "internal_documents"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_document_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    document_type = db.Column(db.String(80), nullable=True)

    owner_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_department_id = db.Column(
        db.Integer,
        db.ForeignKey("departamentos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status = db.Column(
        db.String(32),
        nullable=False,
        default=InternalDocumentStatus.DRAFT,
        index=True,
    )
    is_sensitive = db.Column(db.Boolean, nullable=False, default=False, index=True)

    current_version_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "internal_document_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_internal_documents_current_version_id",
        ),
        nullable=True,
        index=True,
    )

    visibility_mode = db.Column(
        db.String(32),
        nullable=False,
        default=InternalDocumentVisibilityMode.PRIVATE,
        index=True,
    )

    published_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)

    archived_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    archived_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    category = db.relationship(
        "InternalDocumentCategoryORM",
        back_populates="documents",
    )

    owner_user = db.relationship(
        "UserORM",
        foreign_keys=[owner_user_id],
    )
    owner_department = db.relationship(
        "Departamento",
        foreign_keys=[owner_department_id],
    )

    creator = db.relationship(
        "UserORM",
        foreign_keys=[created_by],
    )
    updater = db.relationship(
        "UserORM",
        foreign_keys=[updated_by],
    )
    publisher = db.relationship(
        "UserORM",
        foreign_keys=[published_by],
    )
    archiver = db.relationship(
        "UserORM",
        foreign_keys=[archived_by],
    )

    versions = db.relationship(
        "InternalDocumentVersionORM",
        back_populates="document",
        foreign_keys="InternalDocumentVersionORM.document_id",
        cascade="all, delete-orphan",
        order_by="InternalDocumentVersionORM.version_number.asc()",
    )

    current_version = db.relationship(
        "InternalDocumentVersionORM",
        foreign_keys=[current_version_id],
        post_update=True,
    )

    visibility_rules = db.relationship(
        "InternalDocumentVisibilityORM",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    
    links = db.relationship(
        "InternalDocumentLinkORM",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="InternalDocumentLinkORM.created_at.desc()",
    )

    audit_logs = db.relationship(
        "InternalDocumentAuditLogORM",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="InternalDocumentAuditLogORM.created_at.desc()",
    )
    
    external_resources = db.relationship(
        "InternalDocumentExternalResourceORM",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="InternalDocumentExternalResourceORM.created_at.desc()",
    )

    __table_args__ = (
        db.Index("idx_internal_documents_status_category", "status", "category_id"),
        db.Index("idx_internal_documents_status_created", "status", "created_at"),
        db.Index(
            "idx_internal_documents_visibility_sensitive",
            "visibility_mode",
            "is_sensitive",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InternalDocument id={self.id} title={self.title!r} "
            f"status={self.status!r}>"
        )


class InternalDocumentVersionORM(db.Model):
    __tablename__ = "internal_document_versions"

    id = db.Column(db.Integer, primary_key=True)

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    warehouse_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    version_label = db.Column(db.String(64), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)

    original_filename = db.Column(db.String(255), nullable=True)
    file_mime_type = db.Column(db.String(100), nullable=True)
    file_size_bytes = db.Column(db.BigInteger, nullable=True)
    file_hash_sha256 = db.Column(db.String(64), nullable=True)

    change_notes = db.Column(db.Text, nullable=True)

    is_current = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_hidden_from_users = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    document = db.relationship(
        "InternalDocumentORM",
        back_populates="versions",
        foreign_keys=[document_id],
    )

    warehouse_upload = db.relationship(
        "WarehouseUploadORM",
        foreign_keys=[warehouse_upload_id],
    )

    creator = db.relationship(
        "UserORM",
        foreign_keys=[created_by],
    )

    audit_logs = db.relationship(
        "InternalDocumentAuditLogORM",
        back_populates="version",
        foreign_keys="InternalDocumentAuditLogORM.version_id",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_internal_document_versions_document_version_number",
        ),
        db.UniqueConstraint(
            "document_id",
            "version_label",
            name="uq_internal_document_versions_document_version_label",
        ),
        db.Index(
            "idx_internal_document_versions_document_current",
            "document_id",
            "is_current",
        ),
        db.Index(
            "idx_internal_document_versions_upload",
            "warehouse_upload_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InternalDocumentVersion id={self.id} document_id={self.document_id} "
            f"version={self.version_label!r} current={self.is_current}>"
        )


class InternalDocumentVisibilityORM(db.Model):
    __tablename__ = "internal_document_visibility"

    id = db.Column(db.Integer, primary_key=True)

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    visibility_type = db.Column(db.String(32), nullable=False, index=True)

    role = db.Column(db.String(80), nullable=True, index=True)

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departamentos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    can_view = db.Column(db.Boolean, nullable=False, default=True)
    can_download = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    document = db.relationship(
        "InternalDocumentORM",
        back_populates="visibility_rules",
    )

    department = db.relationship(
        "Departamento",
        foreign_keys=[department_id],
    )

    sucursal = db.relationship(
        "Sucursal",
        foreign_keys=[sucursal_id],
    )

    user = db.relationship(
        "UserORM",
        foreign_keys=[user_id],
    )

    creator = db.relationship(
        "UserORM",
        foreign_keys=[created_by],
    )

    __table_args__ = (
        db.Index(
            "idx_internal_document_visibility_document_active",
            "document_id",
            "is_active",
        ),
        db.Index(
            "idx_internal_document_visibility_type_role",
            "visibility_type",
            "role",
        ),
        db.Index(
            "idx_internal_document_visibility_type_department",
            "visibility_type",
            "department_id",
        ),
        db.Index(
            "idx_internal_document_visibility_type_sucursal",
            "visibility_type",
            "sucursal_id",
        ),
        db.Index(
            "idx_internal_document_visibility_type_user",
            "visibility_type",
            "user_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InternalDocumentVisibility document_id={self.document_id} "
            f"type={self.visibility_type!r}>"
        )

class InternalDocumentLinkORM(db.Model):
    __tablename__ = "internal_document_links"

    id = db.Column(db.Integer, primary_key=True)

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    entity_type = db.Column(db.String(32), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    entity_key = db.Column(db.String(120), nullable=True, index=True)

    link_role = db.Column(db.String(64), nullable=False, index=True)
    label = db.Column(db.String(180), nullable=True)

    is_primary = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    document = db.relationship(
        "InternalDocumentORM",
        back_populates="links",
    )

    creator = db.relationship(
        "UserORM",
        foreign_keys=[created_by],
    )
    updater = db.relationship(
        "UserORM",
        foreign_keys=[updated_by],
    )

    __table_args__ = (
        db.Index(
            "idx_internal_document_links_document_active",
            "document_id",
            "is_active",
        ),
        db.Index(
            "idx_internal_document_links_entity_lookup",
            "entity_type",
            "entity_key",
            "is_active",
        ),
        db.Index(
            "idx_internal_document_links_entity_id_lookup",
            "entity_type",
            "entity_id",
            "is_active",
        ),
        db.Index(
            "idx_internal_document_links_role_primary",
            "link_role",
            "is_primary",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InternalDocumentLink document_id={self.document_id} "
            f"entity_type={self.entity_type!r} entity_key={self.entity_key!r} "
            f"role={self.link_role!r}>"
        )

class InternalDocumentExternalResourceORM(db.Model):
    __tablename__ = "internal_document_external_resources"

    id = db.Column(db.Integer, primary_key=True)

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider = db.Column(db.String(40), nullable=False, index=True)
    resource_kind = db.Column(db.String(40), nullable=False, index=True)

    original_url = db.Column(db.Text, nullable=False)
    external_file_id = db.Column(db.String(255), nullable=True, index=True)
    preview_url = db.Column(db.Text, nullable=True)

    title = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)

    is_primary = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        index=True,
    )

    updated_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    document = db.relationship(
        "InternalDocumentORM",
        back_populates="external_resources",
    )

    creator = db.relationship(
        "UserORM",
        foreign_keys=[created_by],
    )

    updater = db.relationship(
        "UserORM",
        foreign_keys=[updated_by],
    )

    __table_args__ = (
        db.Index(
            "idx_internal_document_external_resources_document_active",
            "document_id",
            "is_active",
        ),
        db.Index(
            "idx_internal_document_external_resources_provider_file",
            "provider",
            "external_file_id",
        ),
        db.Index(
            "idx_internal_document_external_resources_kind_active",
            "resource_kind",
            "is_active",
        ),
        db.Index(
            "idx_internal_document_external_resources_primary",
            "document_id",
            "is_primary",
            "is_active",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InternalDocumentExternalResource id={self.id} "
            f"document_id={self.document_id} provider={self.provider!r} "
            f"kind={self.resource_kind!r}>"
        )

class InternalDocumentAuditLogORM(db.Model):
    __tablename__ = "internal_document_audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version_id = db.Column(
        db.Integer,
        db.ForeignKey("internal_document_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action = db.Column(db.String(80), nullable=False, index=True)

    old_value_json = db.Column(db.JSON, nullable=True)
    new_value_json = db.Column(db.JSON, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)

    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    document = db.relationship(
        "InternalDocumentORM",
        back_populates="audit_logs",
    )

    version = db.relationship(
        "InternalDocumentVersionORM",
        back_populates="audit_logs",
        foreign_keys=[version_id],
    )

    actor = db.relationship(
        "UserORM",
        foreign_keys=[actor_user_id],
    )

    __table_args__ = (
        db.Index(
            "idx_internal_document_audit_document_created",
            "document_id",
            "created_at",
        ),
        db.Index(
            "idx_internal_document_audit_action_created",
            "action",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InternalDocumentAuditLog document_id={self.document_id} "
            f"action={self.action!r}>"
        )