"""Issue 856 B2: append-only channel → candidate Business ID evidence.

Revision ID: c856map1014
Revises: b856port1014
Not used for quota, approvals, authorizations, or provider sends.
"""
from alembic import op
import sqlalchemy as sa

revision = "c856map1014"
down_revision = "b856port1014"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_channel_portfolio_evidence"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_channel_id", sa.String(255), nullable=False),
        sa.Column("business_id", sa.String(32), nullable=True),
        sa.Column("waba_id", sa.String(32), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("evidence_kind", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "(state = 'DECLARED' AND business_id IS NOT NULL) OR "
            "(state = 'WITHDRAWN' AND business_id IS NULL AND waba_id IS NULL)",
            name="ck_mkt_v2_channel_portfolio_state",
        ),
        sa.CheckConstraint("business_id IS NULL OR business_id ~ '^[1-9][0-9]{5,31}$'", name="ck_mkt_v2_channel_portfolio_business"),
        sa.CheckConstraint("waba_id IS NULL OR waba_id ~ '^[1-9][0-9]{5,31}$'", name="ck_mkt_v2_channel_portfolio_waba"),
        sa.CheckConstraint(
            "evidence_kind IN ('OPERATOR_STATEMENT', 'META_DOCUMENT', 'IVENTAS_CONFIRMATION')",
            name="ck_mkt_v2_channel_portfolio_evidence_kind",
        ),
        sa.CheckConstraint(
            "length(trim(provider_channel_id)) > 0 AND length(trim(source_reference)) > 0",
            name="ck_mkt_v2_channel_portfolio_required",
        ),
    )
    op.create_index("ix_mkt_v2_channel_portfolio_latest", TABLE, ["provider_channel_id", "id"])


def downgrade():
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT COUNT(*) FROM " + TABLE)).scalar():
        raise RuntimeError("No se elimina evidencia auditada de asociaciones de canales.")
    op.drop_index("ix_mkt_v2_channel_portfolio_latest", table_name=TABLE)
    op.drop_table(TABLE)
