"""Materialize Campaign V2 multi-child commercial attribution in the worker.

Revision ID: g21c10202601
Revises: a21c10202621
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

revision = "g21c10202601"
down_revision = "a21c10202621"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaign_v2_commercial_results",
        sa.Column("campaign_v2_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_v2_id"],
            ["marketing_campaign_v2_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("campaign_v2_id"),
    )
    op.create_index(
        "ix_mkt_v2_commercial_results_checked",
        "marketing_campaign_v2_commercial_results",
        ["checked_at"],
    )


def downgrade():
    count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM marketing_campaign_v2_commercial_results")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "No es seguro borrar conciliaciones comerciales sin respaldo."
        )
    op.drop_index(
        "ix_mkt_v2_commercial_results_checked",
        table_name="marketing_campaign_v2_commercial_results",
    )
    op.drop_table("marketing_campaign_v2_commercial_results")
