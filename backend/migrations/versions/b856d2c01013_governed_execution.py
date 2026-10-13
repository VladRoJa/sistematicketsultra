"""Issue 856 D2c: independent, single-executor dispatch authorization.

Revision ID: b856d2c01013
Revises: a856d2a01013
"""
from alembic import op
import sqlalchemy as sa

revision = "b856d2c01013"
down_revision = "a856d2a01013"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_governed_executions"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("approval_id", sa.BigInteger(), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(25), nullable=False),
        sa.Column("last_child_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["approval_id"],
                                ["marketing_campaign_v2_dispatch_approvals.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["last_child_id"],
                                ["marketing_campaign_v2_provider_campaigns.id"],
                                ondelete="RESTRICT"),
        sa.UniqueConstraint("approval_id", name="uq_mkt_v2_governed_execution_approval"),
        sa.CheckConstraint("length(manifest_digest) = 64",
                           name="ck_mkt_v2_execution_digest"),
        sa.CheckConstraint(
            "status IN ('AUTHORIZED','IN_FLIGHT','REVIEW_REQUIRED','COMPLETE')",
            name="ck_mkt_v2_execution_status",
        ),
        sa.CheckConstraint("confirmed_at < expires_at", name="ck_mkt_v2_execution_expiry"),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM " + TABLE)).scalar():
        raise RuntimeError("No se borra el historial de autorizaciones.")
    op.drop_table(TABLE)
