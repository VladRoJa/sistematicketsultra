"""Versioned, operator-entered Campaign V2 cost estimates in MXN.

Revision ID: e4b856c9170d
Revises: c7e4a9b2d601
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "e4b856c9170d"
down_revision = "c7e4a9b2d601"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_cost_rate_revisions"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_channel_id", sa.String(255), nullable=False),
        sa.Column("unit_cost_mxn", sa.Numeric(12, 6), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["template_id"], ["marketing_campaign_v2_templates.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "template_id", "provider_channel_id", "valid_from",
            name="uq_mkt_v2_cost_rate_revision",
        ),
        sa.CheckConstraint(
            "unit_cost_mxn > 0 AND unit_cost_mxn <= 1000",
            name="ck_mkt_v2_cost_rate_positive_mxn",
        ),
        sa.CheckConstraint(
            "length(trim(provider_channel_id)) > 0",
            name="ck_mkt_v2_cost_rate_channel",
        ),
        sa.CheckConstraint(
            "length(trim(source_reference)) > 0",
            name="ck_mkt_v2_cost_rate_source",
        ),
    )
    op.create_index(
        "ix_mkt_v2_cost_rate_lookup", TABLE,
        ["template_id", "provider_channel_id", "valid_from"],
    )


def downgrade():
    rows = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM " + TABLE)
    ).scalar()
    if int(rows or 0) > 0:
        raise RuntimeError(
            "Revertir cotizaciones históricas requiere decisión explícita; "
            "no se borrarán versiones."
        )
    op.drop_index("ix_mkt_v2_cost_rate_lookup", table_name=TABLE)
    op.drop_table(TABLE)
