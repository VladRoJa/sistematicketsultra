"""add Campaign V2 tariff overrides

Revision ID: b7c2e9f4a1d6
Revises: f6c1d8a3b2e4
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c2e9f4a1d6"
down_revision = "f6c1d8a3b2e4"
branch_labels = None
depends_on = None


_AUDIENCE_FAMILY_CHECK = (
    "audience_family IN ("
    "'DOMICILIADO', 'TRIMESTRAL', 'CONVENIO', "
    "'SEMESTRE', 'ESTUDIANTE', 'MES', 'OUT_OF_SEGMENT'"
    ")"
)


def upgrade():
    op.create_table(
        "marketing_campaign_v2_tariff_overrides",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tarifa_key", sa.String(length=255), nullable=False),
        sa.Column("tarifa_raw", sa.String(length=255), nullable=False),
        sa.Column("categoria_tarifa", sa.String(length=100), nullable=False),
        sa.Column("audience_family", sa.String(length=30), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
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
            _AUDIENCE_FAMILY_CHECK,
            name="ck_marketing_campaign_v2_tariff_overrides_family",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_marketing_campaign_v2_tariff_overrides_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_marketing_campaign_v2_tariff_overrides_updated_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_campaign_v2_tariff_overrides",
        ),
        sa.UniqueConstraint(
            "tarifa_key",
            name="uq_marketing_campaign_v2_tariff_overrides_tarifa_key",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_tariff_overrides_family",
        "marketing_campaign_v2_tariff_overrides",
        ["audience_family"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_campaign_v2_tariff_overrides_family",
        table_name="marketing_campaign_v2_tariff_overrides",
    )
    op.drop_table("marketing_campaign_v2_tariff_overrides")
