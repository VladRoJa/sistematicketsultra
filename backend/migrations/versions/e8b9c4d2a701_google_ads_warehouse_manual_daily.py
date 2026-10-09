"""Google Ads Warehouse raw report type and immutable daily import ledger.

Revision ID: e8b9c4d2a701
Revises: d4a7c91e2b55
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa


revision = "e8b9c4d2a701"
down_revision = "d4a7c91e2b55"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    family_id = bind.execute(
        sa.text("SELECT id FROM warehouse_families WHERE key = 'reportes_transaccionales'")
    ).scalar_one()
    source_id = bind.execute(
        sa.text("SELECT id FROM warehouse_sources WHERE key = 'manual'")
    ).scalar_one()
    role_id = bind.execute(
        sa.text(
            "SELECT id FROM warehouse_operational_roles "
            "WHERE key = 'FUENTE_AUXILIAR_ENRIQUECIMIENTO'"
        )
    ).scalar_one()
    bind.execute(
        sa.text(
            """
            INSERT INTO warehouse_report_types (
                key, label, family_id, default_source_id,
                default_operational_role_id, default_period_type, active
            )
            SELECT 'google_ads_campaign_daily', 'Google Ads - campañas por día',
                   :family_id, :source_id, :role_id, 'rango', true
            WHERE NOT EXISTS (
                SELECT 1 FROM warehouse_report_types
                WHERE key = 'google_ads_campaign_daily'
            )
            """
        ),
        dict(family_id=family_id, source_id=source_id, role_id=role_id),
    )

    op.create_table(
        "google_ads_daily_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.String(10), nullable=False),
        sa.Column("campaign_id", sa.String(32), nullable=True),
        sa.Column("campaign_key", sa.String(80), nullable=False),
        sa.Column("campaign_name", sa.String(255), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False),
        sa.Column("clicks", sa.BigInteger(), nullable=False),
        sa.Column("conversions", sa.Numeric(18, 4), nullable=False),
        sa.Column("conversion_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column(
            "source_upload_id", sa.Integer(),
            sa.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "customer_id", "campaign_key", "report_date",
            name="uq_google_ads_daily_customer_campaign_day",
        ),
        sa.CheckConstraint("cost >= 0", name="ck_google_ads_daily_cost"),
        sa.CheckConstraint("impressions >= 0", name="ck_google_ads_daily_impressions"),
        sa.CheckConstraint("clicks >= 0", name="ck_google_ads_daily_clicks"),
        sa.CheckConstraint("conversions >= 0", name="ck_google_ads_daily_conversions"),
        sa.CheckConstraint("conversion_value >= 0", name="ck_google_ads_daily_value"),
    )
    op.create_index(
        "ix_google_ads_daily_customer_date", "google_ads_daily_metrics",
        ["customer_id", "report_date"],
    )


def downgrade():
    op.drop_index(
        "ix_google_ads_daily_customer_date", table_name="google_ads_daily_metrics",
    )
    op.drop_table("google_ads_daily_metrics")
    op.execute(
        "DELETE FROM warehouse_report_types "
        "WHERE key = 'google_ads_campaign_daily'"
    )
