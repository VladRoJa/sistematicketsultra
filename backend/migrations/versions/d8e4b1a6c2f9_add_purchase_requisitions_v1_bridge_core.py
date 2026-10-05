"""add purchase requisitions v1 bridge core

Revision ID: d8e4b1a6c2f9
Revises: c3f7a1d9b2e6
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa


revision = "d8e4b1a6c2f9"
down_revision = "c3f7a1d9b2e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "purchase_requisitions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "category",
            sa.String(length=40),
            server_default="GYM_EQUIPMENT",
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column(
            "priority",
            sa.String(length=20),
            server_default="NORMAL",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="PENDING_REVIEW",
            nullable=False,
        ),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_comment", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('GYM_EQUIPMENT')",
            name="ck_purchase_requisitions_category",
        ),
        sa.CheckConstraint(
            "reason IN ('REPLACEMENT', 'NEW_EQUIPMENT', 'DAMAGE', 'EXPANSION', 'OTHER')",
            name="ck_purchase_requisitions_reason",
        ),
        sa.CheckConstraint(
            "priority IN ('NORMAL', 'HIGH', 'CRITICAL')",
            name="ck_purchase_requisitions_priority",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW', 'NEEDS_INFO', 'REJECTED', 'IN_QUOTATION', 'CLOSED')",
            name="ck_purchase_requisitions_status",
        ),
        sa.CheckConstraint(
            "length(trim(justification)) > 0",
            name="ck_purchase_requisitions_justification_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "public_id",
            name="uq_purchase_requisitions_public_id",
        ),
    )
    op.create_index(
        "ix_purchase_requisitions_sucursal_status",
        "purchase_requisitions",
        ["sucursal_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_requisitions_status_created",
        "purchase_requisitions",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "purchase_requisition_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("requisition_id", sa.BigInteger(), nullable=False),
        sa.Column("item_description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(item_description)) > 0",
            name="ck_purchase_requisition_items_description_nonempty",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_purchase_requisition_items_quantity_positive",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["purchase_requisitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purchase_requisition_items_requisition_id",
        "purchase_requisition_items",
        ["requisition_id"],
        unique=False,
    )

    op.create_table(
        "purchase_requisition_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("requisition_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('CREATED', 'INFO_REQUESTED', 'RESUBMITTED', 'APPROVED', 'REJECTED', 'ROUTED_TO_MAINTENANCE', 'ATTACHMENT_ADDED')",
            name="ck_purchase_requisition_events_type",
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN ('PENDING_REVIEW', 'NEEDS_INFO', 'REJECTED', 'IN_QUOTATION', 'CLOSED')",
            name="ck_purchase_requisition_events_from_status",
        ),
        sa.CheckConstraint(
            "to_status IS NULL OR to_status IN ('PENDING_REVIEW', 'NEEDS_INFO', 'REJECTED', 'IN_QUOTATION', 'CLOSED')",
            name="ck_purchase_requisition_events_to_status",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["purchase_requisitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purchase_requisition_events_requisition_created",
        "purchase_requisition_events",
        ["requisition_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "purchase_requisition_attachments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("requisition_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("attachment_type", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attachment_type IN ('EVIDENCE', 'QUOTE', 'OTHER')",
            name="ck_purchase_requisition_attachments_type",
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_purchase_requisition_attachments_size_positive",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["purchase_requisition_events.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["purchase_requisitions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_purchase_requisition_attachments_storage_key",
        ),
    )
    op.create_index(
        "ix_purchase_requisition_attachments_requisition",
        "purchase_requisition_attachments",
        ["requisition_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "purchase_requisition_notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column(
            "channel",
            sa.String(length=20),
            server_default="EMAIL",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('EMAIL')",
            name="ck_purchase_requisition_notifications_channel",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')",
            name="ck_purchase_requisition_notifications_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_purchase_requisition_notifications_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["purchase_requisition_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "recipient_email",
            "channel",
            name="uq_purchase_requisition_notification_delivery",
        ),
    )
    op.create_index(
        "ix_purchase_requisition_notifications_event",
        "purchase_requisition_notifications",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_requisition_notifications_status",
        "purchase_requisition_notifications",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_purchase_requisition_notifications_status",
        table_name="purchase_requisition_notifications",
    )
    op.drop_index(
        "ix_purchase_requisition_notifications_event",
        table_name="purchase_requisition_notifications",
    )
    op.drop_table("purchase_requisition_notifications")

    op.drop_index(
        "ix_purchase_requisition_attachments_requisition",
        table_name="purchase_requisition_attachments",
    )
    op.drop_table("purchase_requisition_attachments")

    op.drop_index(
        "ix_purchase_requisition_events_requisition_created",
        table_name="purchase_requisition_events",
    )
    op.drop_table("purchase_requisition_events")

    op.drop_index(
        "ix_purchase_requisition_items_requisition_id",
        table_name="purchase_requisition_items",
    )
    op.drop_table("purchase_requisition_items")

    op.drop_index(
        "ix_purchase_requisitions_status_created",
        table_name="purchase_requisitions",
    )
    op.drop_index(
        "ix_purchase_requisitions_sucursal_status",
        table_name="purchase_requisitions",
    )
    op.drop_table("purchase_requisitions")
