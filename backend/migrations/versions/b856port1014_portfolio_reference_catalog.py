"""Issue 856 B1: operator-declared Meta business IDs, explicitly unverified.

Revision ID: b856port1014
Revises: f856opcap1013

No seed, channel assignment, quota activation or provider access.
"""
from alembic import op
import sqlalchemy as sa

revision = "b856port1014"
down_revision = "f856opcap1013"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_portfolio_references"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=True),
        sa.Column("app_id", sa.String(32), nullable=True),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("business_id ~ '^[1-9][0-9]{5,31}$'", name="ck_mkt_v2_portfolio_business_id"),
        sa.CheckConstraint("app_id IS NULL OR app_id ~ '^[1-9][0-9]{5,31}$'", name="ck_mkt_v2_portfolio_app_id"),
        sa.CheckConstraint("length(trim(source_reference)) > 0", name="ck_mkt_v2_portfolio_source"),
    )
    op.create_index("ix_mkt_v2_portfolio_business_latest", TABLE, ["business_id", "id"])


def downgrade():
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT COUNT(*) FROM " + TABLE)).scalar()
    if int(count or 0):
        raise RuntimeError("No se eliminan referencias de portafolio auditadas.")
    op.drop_index("ix_mkt_v2_portfolio_business_latest", table_name=TABLE)
    op.drop_table(TABLE)
