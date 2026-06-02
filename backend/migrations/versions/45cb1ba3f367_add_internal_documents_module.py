"""add internal documents module

Revision ID: 45cb1ba3f367
Revises: 301dbee2f6cd
Create Date: 2026-06-02 12:35:47.873116

"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "45cb1ba3f367"
down_revision = "301dbee2f6cd"
branch_labels = None
depends_on = None


def _utc_now():
    return datetime.now(timezone.utc)


def upgrade():
    now = _utc_now()

    op.create_table(
        "internal_document_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("internal_document_categories", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_internal_document_categories_key"),
            ["key"],
            unique=True,
        )

    categories_table = sa.table(
        "internal_document_categories",
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    op.bulk_insert(
        categories_table,
        [
            {
                "key": "REPORTES",
                "name": "Reportes",
                "description": "Reportes operativos, comerciales, administrativos o de BI publicados para consulta interna.",
                "is_active": True,
                "sort_order": 10,
                "created_at": now,
                "updated_at": now,
            },
            {
                "key": "MANUALES",
                "name": "Manuales",
                "description": "Manuales de uso, operación, capacitación o consulta interna.",
                "is_active": True,
                "sort_order": 20,
                "created_at": now,
                "updated_at": now,
            },
            {
                "key": "POLITICAS",
                "name": "Políticas",
                "description": "Políticas internas vigentes o documentadas para referencia corporativa.",
                "is_active": True,
                "sort_order": 30,
                "created_at": now,
                "updated_at": now,
            },
            {
                "key": "FORMATOS",
                "name": "Formatos",
                "description": "Formatos descargables para procesos internos.",
                "is_active": True,
                "sort_order": 40,
                "created_at": now,
                "updated_at": now,
            },
            {
                "key": "PROCEDIMIENTOS",
                "name": "Procedimientos",
                "description": "Procedimientos operativos, administrativos o técnicos.",
                "is_active": True,
                "sort_order": 50,
                "created_at": now,
                "updated_at": now,
            },
            {
                "key": "TUTORIALES",
                "name": "Tutoriales",
                "description": "Tutoriales, guías rápidas y material de apoyo.",
                "is_active": True,
                "sort_order": 60,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )

    op.create_table(
        "internal_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("owner_department_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("visibility_mode", sa.String(length=32), nullable=False),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["archived_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["internal_document_categories.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["owner_department_id"],
            ["departamentos.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("internal_documents", schema=None) as batch_op:
        batch_op.create_index(
            "idx_internal_documents_status_category",
            ["status", "category_id"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_documents_status_created",
            ["status", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_documents_visibility_sensitive",
            ["visibility_mode", "is_sensitive"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_archived_by"),
            ["archived_by"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_category_id"),
            ["category_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_created_by"),
            ["created_by"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_current_version_id"),
            ["current_version_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_is_sensitive"),
            ["is_sensitive"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_owner_department_id"),
            ["owner_department_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_owner_user_id"),
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_published_by"),
            ["published_by"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_title"),
            ["title"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_updated_by"),
            ["updated_by"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_documents_visibility_mode"),
            ["visibility_mode"],
            unique=False,
        )

    op.create_table(
        "internal_document_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_upload_id", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("file_mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("file_hash_sha256", sa.String(length=64), nullable=True),
        sa.Column("change_notes", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("is_hidden_from_users", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["internal_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_upload_id"],
            ["warehouse_uploads.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "version_label",
            name="uq_internal_document_versions_document_version_label",
        ),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_internal_document_versions_document_version_number",
        ),
    )

    with op.batch_alter_table("internal_document_versions", schema=None) as batch_op:
        batch_op.create_index(
            "idx_internal_document_versions_document_current",
            ["document_id", "is_current"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_versions_upload",
            ["warehouse_upload_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_versions_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_versions_created_by"),
            ["created_by"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_versions_document_id"),
            ["document_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_versions_is_current"),
            ["is_current"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_versions_is_hidden_from_users"),
            ["is_hidden_from_users"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_versions_warehouse_upload_id"),
            ["warehouse_upload_id"],
            unique=False,
        )

    op.create_foreign_key(
        "fk_internal_documents_current_version_id",
        "internal_documents",
        "internal_document_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "internal_document_visibility",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("visibility_type", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("sucursal_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("can_view", sa.Boolean(), nullable=False),
        sa.Column("can_download", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departamentos.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["internal_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("internal_document_visibility", schema=None) as batch_op:
        batch_op.create_index(
            "idx_internal_document_visibility_document_active",
            ["document_id", "is_active"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_visibility_type_department",
            ["visibility_type", "department_id"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_visibility_type_role",
            ["visibility_type", "role"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_visibility_type_sucursal",
            ["visibility_type", "sucursal_id"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_visibility_type_user",
            ["visibility_type", "user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_created_by"),
            ["created_by"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_department_id"),
            ["department_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_document_id"),
            ["document_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_is_active"),
            ["is_active"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_role"),
            ["role"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_sucursal_id"),
            ["sucursal_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_user_id"),
            ["user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_visibility_visibility_type"),
            ["visibility_type"],
            unique=False,
        )

    op.create_table(
        "internal_document_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("old_value_json", sa.JSON(), nullable=True),
        sa.Column("new_value_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["internal_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["internal_document_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("internal_document_audit_logs", schema=None) as batch_op:
        batch_op.create_index(
            "idx_internal_document_audit_action_created",
            ["action", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_audit_document_created",
            ["document_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_audit_logs_action"),
            ["action"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_audit_logs_actor_user_id"),
            ["actor_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_audit_logs_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_audit_logs_document_id"),
            ["document_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_audit_logs_version_id"),
            ["version_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("internal_document_audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_internal_document_audit_logs_version_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_audit_logs_document_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_audit_logs_created_at"))
        batch_op.drop_index(batch_op.f("ix_internal_document_audit_logs_actor_user_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_audit_logs_action"))
        batch_op.drop_index("idx_internal_document_audit_document_created")
        batch_op.drop_index("idx_internal_document_audit_action_created")

    op.drop_table("internal_document_audit_logs")

    with op.batch_alter_table("internal_document_visibility", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_visibility_type"))
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_user_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_sucursal_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_role"))
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_is_active"))
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_document_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_department_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_created_by"))
        batch_op.drop_index(batch_op.f("ix_internal_document_visibility_created_at"))
        batch_op.drop_index("idx_internal_document_visibility_type_user")
        batch_op.drop_index("idx_internal_document_visibility_type_sucursal")
        batch_op.drop_index("idx_internal_document_visibility_type_role")
        batch_op.drop_index("idx_internal_document_visibility_type_department")
        batch_op.drop_index("idx_internal_document_visibility_document_active")

    op.drop_table("internal_document_visibility")

    op.drop_constraint(
        "fk_internal_documents_current_version_id",
        "internal_documents",
        type_="foreignkey",
    )

    with op.batch_alter_table("internal_document_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_internal_document_versions_warehouse_upload_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_versions_is_hidden_from_users"))
        batch_op.drop_index(batch_op.f("ix_internal_document_versions_is_current"))
        batch_op.drop_index(batch_op.f("ix_internal_document_versions_document_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_versions_created_by"))
        batch_op.drop_index(batch_op.f("ix_internal_document_versions_created_at"))
        batch_op.drop_index("idx_internal_document_versions_upload")
        batch_op.drop_index("idx_internal_document_versions_document_current")

    op.drop_table("internal_document_versions")

    with op.batch_alter_table("internal_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_internal_documents_visibility_mode"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_updated_by"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_title"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_status"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_published_by"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_owner_user_id"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_owner_department_id"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_is_sensitive"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_current_version_id"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_created_by"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_created_at"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_category_id"))
        batch_op.drop_index(batch_op.f("ix_internal_documents_archived_by"))
        batch_op.drop_index("idx_internal_documents_visibility_sensitive")
        batch_op.drop_index("idx_internal_documents_status_created")
        batch_op.drop_index("idx_internal_documents_status_category")

    op.drop_table("internal_documents")

    with op.batch_alter_table("internal_document_categories", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_internal_document_categories_key"))

    op.drop_table("internal_document_categories")