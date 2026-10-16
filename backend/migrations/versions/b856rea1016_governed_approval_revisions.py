"""Version immutable Campaign V2 approvals for explicit unattempted reauthorization.

Revision ID: b856rea1016
Revises: a9c6b2e4f150

Existing approvals keep revision 1, existing children and execution untouched.
No timestamps or send status are changed.
"""
from alembic import op
import sqlalchemy as sa

revision = "b856rea1016"
down_revision = "a9c6b2e4f150"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_dispatch_approvals"
OLD = "uq_mkt_v2_approval_campaign"
NEW = "uq_mkt_v2_approval_campaign_revision"
CHECK = "ck_mkt_v2_approval_revision_positive"


def upgrade():
    op.add_column(
        TABLE, sa.Column("revision_no", sa.Integer(), nullable=False, server_default="1")
    )
    op.drop_constraint(OLD, TABLE, type_="unique")
    op.create_unique_constraint(NEW, TABLE, ["campaign_v2_id", "revision_no"])
    op.create_check_constraint(CHECK, TABLE, "revision_no >= 1")


def downgrade():
    conn = op.get_bind()
    multiple = conn.execute(sa.text(
        f"SELECT EXISTS(SELECT 1 FROM {TABLE} GROUP BY campaign_v2_id HAVING COUNT(*) > 1)"
    )).scalar()
    if multiple:
        raise RuntimeError("Existen reautorizaciones; downgrade destructivo prohibido.")
    op.drop_constraint(CHECK, TABLE, type_="check")
    op.drop_constraint(NEW, TABLE, type_="unique")
    op.create_unique_constraint(OLD, TABLE, ["campaign_v2_id"])
    op.drop_column(TABLE, "revision_no")
