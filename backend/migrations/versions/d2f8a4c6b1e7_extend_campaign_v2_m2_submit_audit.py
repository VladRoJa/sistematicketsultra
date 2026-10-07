"""extend Campaign V2 M2 submit audit

Revision ID: d2f8a4c6b1e7
Revises: c1f7e9a4b6d2
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "d2f8a4c6b1e7"
down_revision = "c1f7e9a4b6d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "marketing_campaign_v2_provider_campaigns",
        sa.Column("submit_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marketing_campaign_v2_provider_campaigns",
        sa.Column("provider_deduplicated", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "marketing_campaign_v2_provider_campaigns",
        sa.Column(
            "request_snapshot_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "marketing_campaign_v2_provider_campaigns",
        sa.Column(
            "provider_response_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column(
        "marketing_campaign_v2_provider_campaigns",
        "provider_response_json",
    )
    op.drop_column(
        "marketing_campaign_v2_provider_campaigns",
        "request_snapshot_json",
    )
    op.drop_column(
        "marketing_campaign_v2_provider_campaigns",
        "provider_deduplicated",
    )
    op.drop_column(
        "marketing_campaign_v2_provider_campaigns",
        "submit_started_at",
    )
