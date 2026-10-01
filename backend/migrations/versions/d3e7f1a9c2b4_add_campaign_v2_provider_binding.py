"""add Campaign V2 provider binding

Revision ID: d3e7f1a9c2b4
Revises: b7c2e9f4a1d6
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa


revision = "d3e7f1a9c2b4"
down_revision = "b7c2e9f4a1d6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "marketing_campaign_v2_campaigns",
        sa.Column("provider", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "marketing_campaign_v2_campaigns",
        sa.Column("provider_campaign_id", sa.String(length=255), nullable=True),
    )
    op.create_check_constraint(
        "ck_marketing_campaign_v2_campaigns_provider_binding_complete",
        "marketing_campaign_v2_campaigns",
        "(provider IS NULL AND provider_campaign_id IS NULL) OR "
        "(provider IS NOT NULL AND provider_campaign_id IS NOT NULL "
        "AND length(trim(provider)) > 0 "
        "AND length(trim(provider_campaign_id)) > 0 "
        "AND provider = upper(trim(provider)) "
        "AND provider_campaign_id = trim(provider_campaign_id))",
    )
    op.create_unique_constraint(
        "uq_marketing_campaign_v2_campaigns_provider_identity",
        "marketing_campaign_v2_campaigns",
        ["provider", "provider_campaign_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_marketing_campaign_v2_campaigns_provider_identity",
        "marketing_campaign_v2_campaigns",
        type_="unique",
    )
    op.drop_constraint(
        "ck_marketing_campaign_v2_campaigns_provider_binding_complete",
        "marketing_campaign_v2_campaigns",
        type_="check",
    )
    op.drop_column(
        "marketing_campaign_v2_campaigns",
        "provider_campaign_id",
    )
    op.drop_column(
        "marketing_campaign_v2_campaigns",
        "provider",
    )
