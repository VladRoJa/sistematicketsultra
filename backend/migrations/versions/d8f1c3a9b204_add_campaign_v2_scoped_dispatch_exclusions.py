"""add campaign scoped dispatch exclusions without editing frozen recipients

Revision ID: d8f1c3a9b204
Revises: f3f1d4e6a7c9
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "d8f1c3a9b204"
down_revision = "f3f1d4e6a7c9"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_recipient_dispatch_exclusions"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["marketing_campaign_v2_campaigns.id"],
            ondelete="CASCADE", name="fk_mkt_v2_dispatch_exclusions_campaign",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["marketing_campaign_v2_recipients.id"],
            ondelete="CASCADE", name="fk_mkt_v2_dispatch_exclusions_recipient",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"],
            ondelete="RESTRICT", name="fk_mkt_v2_dispatch_exclusions_actor",
        ),
        sa.UniqueConstraint(
            "campaign_id", "recipient_id",
            name="uq_mkt_v2_recipient_dispatch_exclusions_campaign_recipient",
        ),
        sa.CheckConstraint(
            "reason = 'AMBIGUOUS_BRANCH_EVIDENCE'",
            name="ck_mkt_v2_recipient_dispatch_exclusion_reason",
        ),
    )
    op.create_index(
        "ix_mkt_v2_dispatch_exclusions_recipient_id",
        TABLE, ["recipient_id"],
    )


def downgrade():
    op.drop_index("ix_mkt_v2_dispatch_exclusions_recipient_id", table_name=TABLE)
    op.drop_table(TABLE)
