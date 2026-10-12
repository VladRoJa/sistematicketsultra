"""Allow audited suppression of numbers already submitted in prior campaigns.

Revision ID: c29f6a8d1e70
Revises: b14d9e2c6f80
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

revision = "c29f6a8d1e70"
down_revision = "b14d9e2c6f80"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_recipient_dispatch_exclusions"
REASON = "ck_mkt_v2_recipient_dispatch_exclusion_reason"
DIFFERENT = "ck_mkt_v2_recipient_dispatch_exclusion_source_diff"
FK = "fk_mkt_v2_dispatch_exclusions_related_campaign"


def upgrade():
    op.add_column(TABLE, sa.Column("related_campaign_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        FK, TABLE, "marketing_campaign_v2_campaigns",
        ["related_campaign_id"], ["id"], ondelete="RESTRICT",
    )
    op.drop_constraint(REASON, TABLE, type_="check")
    op.create_check_constraint(
        REASON, TABLE,
        "(reason = 'AMBIGUOUS_BRANCH_EVIDENCE' AND related_campaign_id IS NULL)"
        " OR (reason = 'PREVIOUS_CAMPAIGN_CONTACT' AND related_campaign_id IS NOT NULL)",
    )
    op.create_check_constraint(
        DIFFERENT, TABLE,
        "related_campaign_id IS NULL OR related_campaign_id <> campaign_id",
    )


def downgrade():
    # Downgrade must never silently discard new audited exclusions.
    connection = op.get_bind()
    count = connection.execute(
        sa.text(
            "SELECT count(*) FROM " + TABLE +
            " WHERE reason = 'PREVIOUS_CAMPAIGN_CONTACT'"
        )
    ).scalar()
    if int(count or 0):
        raise RuntimeError(
            "No se puede revertir: existen exclusiones PREVIOUS_CAMPAIGN_CONTACT."
        )
    op.drop_constraint(DIFFERENT, TABLE, type_="check")
    op.drop_constraint(REASON, TABLE, type_="check")
    op.create_check_constraint(
        REASON, TABLE, "reason = 'AMBIGUOUS_BRANCH_EVIDENCE'",
    )
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.drop_column(TABLE, "related_campaign_id")
