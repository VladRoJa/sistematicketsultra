"""add Campaign V2 blacklist

Revision ID: c6f4b9a2d7e1
Revises: b5d9e2a7c1f4
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa


revision = "c6f4b9a2d7e1"
down_revision = "b5d9e2a7c1f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaign_v2_blacklist",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("phone_mx10", sa.String(length=10), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(phone_mx10) = 10",
            name="ck_marketing_campaign_v2_blacklist_phone_length",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "phone_mx10",
            name="uq_marketing_campaign_v2_blacklist_phone_mx10",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_blacklist_created_at",
        "marketing_campaign_v2_blacklist",
        ["created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_campaign_v2_blacklist_created_at",
        table_name="marketing_campaign_v2_blacklist",
    )
    op.drop_table("marketing_campaign_v2_blacklist")
