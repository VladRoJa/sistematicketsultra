"""add internal document external resources

Revision ID: 1f0f74cb05c8
Revises: b0b8fe202886
Create Date: 2026-06-18 08:27:39.933997

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f0f74cb05c8'
down_revision = 'b0b8fe202886'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "internal_document_external_resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("resource_kind", sa.String(length=40), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("external_file_id", sa.String(length=255), nullable=True),
        sa.Column("preview_url", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["internal_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("internal_document_external_resources", schema=None) as batch_op:
        batch_op.create_index(
            "idx_internal_document_external_resources_document_active",
            ["document_id", "is_active"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_external_resources_kind_active",
            ["resource_kind", "is_active"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_external_resources_primary",
            ["document_id", "is_primary", "is_active"],
            unique=False,
        )
        batch_op.create_index(
            "idx_internal_document_external_resources_provider_file",
            ["provider", "external_file_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_created_by"),
            ["created_by"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_document_id"),
            ["document_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_external_file_id"),
            ["external_file_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_is_active"),
            ["is_active"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_is_primary"),
            ["is_primary"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_provider"),
            ["provider"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_resource_kind"),
            ["resource_kind"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_internal_document_external_resources_updated_by"),
            ["updated_by"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("internal_document_external_resources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_updated_by"))
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_resource_kind"))
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_provider"))
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_is_primary"))
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_is_active"))
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_external_file_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_document_id"))
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_created_by"))
        batch_op.drop_index(batch_op.f("ix_internal_document_external_resources_created_at"))
        batch_op.drop_index("idx_internal_document_external_resources_provider_file")
        batch_op.drop_index("idx_internal_document_external_resources_primary")
        batch_op.drop_index("idx_internal_document_external_resources_kind_active")
        batch_op.drop_index("idx_internal_document_external_resources_document_active")

    op.drop_table("internal_document_external_resources")