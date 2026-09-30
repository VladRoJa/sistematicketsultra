"""add marketing campaign v2 persistence

Revision ID: a4d8c2e6f1b5
Revises: c3a7e1f5b9d2
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "a4d8c2e6f1b5"
down_revision = "c3a7e1f5b9d2"
branch_labels = None
depends_on = None


_PURPOSE_CHECK = (
    "purpose IN ('NEW_SALE', 'REACTIVATION', 'ACTIVE_MEMBERS', 'UNCLASSIFIED')"
)
_AUDIENCE_FAMILY_CHECK = (
    "audience_family IS NULL OR audience_family IN ("
    "'DOMICILIADO', 'TRIMESTRAL', 'CONVENIO', "
    "'SEMESTRE', 'ESTUDIANTE', 'MES', 'OUT_OF_SEGMENT'"
    ")"
)


def upgrade():
    op.create_table(
        "marketing_campaign_v2_campaigns",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "purpose",
            sa.String(length=30),
            server_default=sa.text("'UNCLASSIFIED'"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column(
            "audience_definition_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "frozen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            _PURPOSE_CHECK,
            name="ck_marketing_campaign_v2_campaigns_purpose",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_marketing_campaign_v2_campaigns_created_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_campaign_v2_campaigns",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_campaigns_created_at",
        "marketing_campaign_v2_campaigns",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_campaigns_purpose",
        "marketing_campaign_v2_campaigns",
        ["purpose"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_campaigns_source",
        "marketing_campaign_v2_campaigns",
        ["source"],
        unique=False,
    )

    op.create_table(
        "marketing_campaign_v2_recipients",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("phone_mx10", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("socios_vencidos_cartera_id", sa.BigInteger(), nullable=True),
        sa.Column("socios_activos_snapshot_row_id", sa.BigInteger(), nullable=True),
        sa.Column("member_id", sa.String(length=64), nullable=True),
        sa.Column("member_pin", sa.String(length=64), nullable=True),
        sa.Column("member_name", sa.String(length=255), nullable=True),
        sa.Column("sucursal", sa.String(length=255), nullable=True),
        sa.Column("tarifa_raw", sa.String(length=255), nullable=True),
        sa.Column("categoria_tarifa", sa.String(length=100), nullable=True),
        sa.Column("audience_family", sa.String(length=30), nullable=True),
        sa.Column("fecha_vencimiento_date", sa.Date(), nullable=True),
        sa.Column("inclusion_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(phone_mx10) = 10",
            name="ck_marketing_campaign_v2_recipients_phone_mx10_length",
        ),
        sa.CheckConstraint(
            _AUDIENCE_FAMILY_CHECK,
            name="ck_marketing_campaign_v2_recipients_audience_family",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["marketing_campaign_v2_campaigns.id"],
            name="fk_marketing_campaign_v2_recipients_campaign_id_campaigns",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["socios_vencidos_cartera_id"],
            ["socios_vencidos_cartera.id"],
            name="fk_marketing_campaign_v2_recipients_vencidos_cartera_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["socios_activos_snapshot_row_id"],
            ["socios_activos_snapshot_rows.id"],
            name="fk_marketing_campaign_v2_recipients_activos_snapshot_row_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_campaign_v2_recipients",
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "phone_mx10",
            name="uq_marketing_campaign_v2_recipients_campaign_phone",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_recipients_campaign_id",
        "marketing_campaign_v2_recipients",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_recipients_phone_mx10",
        "marketing_campaign_v2_recipients",
        ["phone_mx10"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_recipients_vencidos_cartera_id",
        "marketing_campaign_v2_recipients",
        ["socios_vencidos_cartera_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_recipients_activos_snapshot_row_id",
        "marketing_campaign_v2_recipients",
        ["socios_activos_snapshot_row_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_campaign_v2_recipients_activos_snapshot_row_id",
        table_name="marketing_campaign_v2_recipients",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_recipients_vencidos_cartera_id",
        table_name="marketing_campaign_v2_recipients",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_recipients_phone_mx10",
        table_name="marketing_campaign_v2_recipients",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_recipients_campaign_id",
        table_name="marketing_campaign_v2_recipients",
    )
    op.drop_table("marketing_campaign_v2_recipients")

    op.drop_index(
        "ix_marketing_campaign_v2_campaigns_source",
        table_name="marketing_campaign_v2_campaigns",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_campaigns_purpose",
        table_name="marketing_campaign_v2_campaigns",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_campaigns_created_at",
        table_name="marketing_campaign_v2_campaigns",
    )
    op.drop_table("marketing_campaign_v2_campaigns")
