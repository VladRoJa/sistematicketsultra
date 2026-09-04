"""add marketing reactivation campaigns

Revision ID: d9f4b2c7e1a6
Revises: c8e3a1b64d95
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "d9f4b2c7e1a6"
down_revision = "c8e3a1b64d95"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_reactivation_campaigns",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "exported_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "date_from <= date_to",
            name="ck_marketing_reactivation_campaigns_date_range",
        ),
        sa.CheckConstraint(
            "recipient_count >= 0",
            name="ck_marketing_reactivation_campaigns_recipient_count",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'EXPORTED', 'SENT', 'CANCELLED')",
            name="ck_marketing_reactivation_campaigns_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_marketing_reactivation_campaigns_created_by_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_reactivation_campaigns",
        ),
    )
    op.create_index(
        "ix_marketing_reactivation_campaigns_created_at",
        "marketing_reactivation_campaigns",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_reactivation_campaigns_status",
        "marketing_reactivation_campaigns",
        ["status"],
        unique=False,
    )

    op.create_table(
        "marketing_reactivation_campaign_recipients",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "socios_vencidos_cartera_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column("phone_mx10", sa.String(length=10), nullable=False),
        sa.Column("member_name", sa.String(length=255), nullable=True),
        sa.Column("sucursal", sa.String(length=255), nullable=False),
        sa.Column("fecha_vencimiento_date", sa.Date(), nullable=False),
        sa.Column("tarifa", sa.String(length=255), nullable=True),
        sa.Column("inclusion_status", sa.String(length=40), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=100), nullable=True),
        sa.Column("operational_status", sa.String(length=50), nullable=False),
        sa.Column("operational_reason", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["marketing_reactivation_campaigns.id"],
            name="fk_marketing_reactivation_recipients_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["socios_vencidos_cartera_id"],
            ["socios_vencidos_cartera.id"],
            name="fk_marketing_reactivation_recipients_cartera",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_reactivation_campaign_recipients",
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "phone_mx10",
            name="uq_marketing_reactivation_recipients_campaign_phone",
        ),
    )
    op.create_index(
        "ix_marketing_reactivation_recipients_campaign_id",
        "marketing_reactivation_campaign_recipients",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_reactivation_recipients_phone_mx10",
        "marketing_reactivation_campaign_recipients",
        ["phone_mx10"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_reactivation_recipients_phone_mx10",
        table_name="marketing_reactivation_campaign_recipients",
    )
    op.drop_index(
        "ix_marketing_reactivation_recipients_campaign_id",
        table_name="marketing_reactivation_campaign_recipients",
    )
    op.drop_table("marketing_reactivation_campaign_recipients")
    op.drop_index(
        "ix_marketing_reactivation_campaigns_status",
        table_name="marketing_reactivation_campaigns",
    )
    op.drop_index(
        "ix_marketing_reactivation_campaigns_created_at",
        table_name="marketing_reactivation_campaigns",
    )
    op.drop_table("marketing_reactivation_campaigns")
