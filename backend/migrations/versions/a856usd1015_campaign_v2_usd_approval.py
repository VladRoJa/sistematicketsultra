"""Issue 856: nullable legacy MXN and immutable USD cost approvals.

Revision ID: a856usd1015
Revises: f6roster1014

Non-retroactive: old approvals keep MXN, new approvals persist USD. This
migration does NOT touch existing campaigns, provider children or send flags.
"""
from alembic import op
import sqlalchemy as sa

revision = "a856usd1015"
down_revision = "f6roster1014"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_dispatch_approvals"
CHECK = "ck_mkt_v2_approval_exactly_one_currency"


def upgrade():
    op.alter_column(TABLE, "approved_estimated_mxn",
                    existing_type=sa.Numeric(14, 2), nullable=True)
    op.add_column(TABLE, sa.Column("approved_estimated_usd",
                                  sa.Numeric(14, 4), nullable=True))
    op.create_check_constraint(
        CHECK, TABLE,
        "(approved_estimated_mxn IS NOT NULL AND approved_estimated_usd IS NULL) OR "
        "(approved_estimated_mxn IS NULL AND approved_estimated_usd IS NOT NULL "
        "AND approved_estimated_usd >= 0)",
    )


def downgrade():
    # Never discard USD approvals on rollback.
    conn = op.get_bind()
    if conn.execute(sa.text(
        f"SELECT EXISTS(SELECT 1 FROM {TABLE} "
        "WHERE approved_estimated_usd IS NOT NULL)"
    )).scalar():
        raise RuntimeError("USD approvals exist; refuse destructive migration downgrade.")
    op.drop_constraint(CHECK, TABLE, type_="check")
    op.drop_column(TABLE, "approved_estimated_usd")
    op.alter_column(TABLE, "approved_estimated_mxn",
                    existing_type=sa.Numeric(14, 2), nullable=False)
