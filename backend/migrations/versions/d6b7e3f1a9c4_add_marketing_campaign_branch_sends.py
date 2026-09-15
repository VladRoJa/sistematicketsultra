"""add marketing campaign branch sends

Revision ID: d6b7e3f1a9c4
Revises: c4e7a9b2d6f1
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa


revision = "d6b7e3f1a9c4"
down_revision = "c4e7a9b2d6f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_reactivation_campaign_branch_sends",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("sucursal", sa.String(length=255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["marketing_reactivation_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sent_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "sucursal",
            name="uq_marketing_reactivation_branch_send_campaign_branch",
        ),
    )
    op.create_index(
        "ix_marketing_reactivation_branch_send_campaign_id",
        "marketing_reactivation_campaign_branch_sends",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_reactivation_branch_send_sent_at",
        "marketing_reactivation_campaign_branch_sends",
        ["sent_at"],
        unique=False,
    )

    # Legacy campaigns marked SENT represented one global send timestamp.
    # Freeze that historical fact per branch so the new attribution model is
    # backward compatible from the moment this migration is applied.
    op.execute(
        sa.text(
            """
            INSERT INTO marketing_reactivation_campaign_branch_sends
                (campaign_id, sucursal, sent_at, sent_by_user_id, created_at)
            SELECT
                c.id,
                r.sucursal,
                c.sent_at,
                NULL,
                COALESCE(c.sent_at, c.updated_at, CURRENT_TIMESTAMP)
            FROM marketing_reactivation_campaigns c
            JOIN marketing_reactivation_campaign_recipients r
              ON r.campaign_id = c.id
            WHERE c.status = 'SENT'
              AND c.sent_at IS NOT NULL
            GROUP BY c.id, r.sucursal, c.sent_at, c.updated_at
            ON CONFLICT (campaign_id, sucursal) DO NOTHING
            """
        )
    )


def downgrade():
    op.drop_index(
        "ix_marketing_reactivation_branch_send_sent_at",
        table_name="marketing_reactivation_campaign_branch_sends",
    )
    op.drop_index(
        "ix_marketing_reactivation_branch_send_campaign_id",
        table_name="marketing_reactivation_campaign_branch_sends",
    )
    op.drop_table("marketing_reactivation_campaign_branch_sends")
