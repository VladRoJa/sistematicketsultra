"""Materialized read-only Campaign V2 M2 sale-month totals, without phones.

Revision ID: m1234m2sales111826
Revises: m1233bimulti111026
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa


revision = "m1234m2sales111826"
down_revision = "m1233bimulti111026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaign_v2_commercial_sale_months",
        sa.Column("sale_from", sa.Date(), nullable=False),
        sa.Column("sale_to", sa.Date(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "sale_from", "sale_to", "window_days",
            name="pk_mkt_v2_commercial_sale_months",
        ),
        sa.CheckConstraint(
            "window_days IN (7, 14, 30)",
            name="ck_mkt_v2_sale_month_window_days",
        ),
        sa.CheckConstraint(
            "sale_to >= sale_from",
            name="ck_mkt_v2_sale_month_date_order",
        ),
    )
    op.create_index(
        "ix_mkt_v2_sale_month_checked_at",
        "marketing_campaign_v2_commercial_sale_months",
        ["checked_at"],
    )


def downgrade():
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM marketing_campaign_v2_commercial_sale_months")
    ).scalar_one()
    if count:
        raise RuntimeError("No se pueden borrar conciliaciones M2 sin respaldo.")
    op.drop_index(
        "ix_mkt_v2_sale_month_checked_at",
        table_name="marketing_campaign_v2_commercial_sale_months",
    )
    op.drop_table("marketing_campaign_v2_commercial_sale_months")
