"""create ticket attachments

Revision ID: d3a4f71c9b82
Revises: 079b090bd487
Create Date: 2026-08-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d3a4f71c9b82"
down_revision = "079b090bd487"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ticket_attachments",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "original_filename",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "storage_key",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "mime_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "size_bytes",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "width",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "height",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "optimization_mode",
            sa.String(length=32),
            nullable=False,
            server_default="original",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "emailed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "delete_after",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_ticket_attachments_storage_key",
        ),
    )

    op.create_index(
        "ix_ticket_attachments_ticket_id",
        "ticket_attachments",
        ["ticket_id"],
        unique=False,
    )

    op.create_index(
        "ix_ticket_attachments_cleanup",
        "ticket_attachments",
        ["deleted_at", "delete_after"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_ticket_attachments_cleanup",
        table_name="ticket_attachments",
    )

    op.drop_index(
        "ix_ticket_attachments_ticket_id",
        table_name="ticket_attachments",
    )

    op.drop_table("ticket_attachments")
