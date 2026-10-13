"""M5 Google Ads: schema for explicitly approved branch identities.

Revision ID: c7e4a9b2d601
Revises: b14d9e2c6f80
Create Date: 2026-10-12

Schema only. NO seed, attribution, Funnel change, or Warehouse fact updates.
The separately approved historical manifest is not automatically ingested.
"""
from alembic import op
import sqlalchemy as sa


revision = "c7e4a9b2d601"
down_revision = "b14d9e2c6f80"
branch_labels = None
depends_on = None

TABLE = "google_ads_branch_identity_mappings"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.String(10), nullable=False),
        sa.Column("campaign_key", sa.String(80), nullable=False),
        sa.Column("ad_group_key", sa.String(80), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("source_upload_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("approval_status", sa.String(40), nullable=False),
        sa.Column("approval_reference", sa.String(255), nullable=False),
        sa.Column("approved_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "customer_id", "campaign_key", "ad_group_key",
            name="uq_google_ads_m5_identity",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"], ["track_branch_catalog.sucursal_canon"],
            name="fk_google_ads_m5_branch", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_upload_id"], ["warehouse_uploads.id"],
            name="fk_google_ads_m5_upload", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "customer_id ~ '^[0-9]{10}$'",
            name="ck_google_ads_m5_customer",
        ),
        sa.CheckConstraint(
            "campaign_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_google_ads_m5_campaign_key",
        ),
        sa.CheckConstraint(
            "ad_group_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_google_ads_m5_ad_group_key",
        ),
        sa.CheckConstraint(
            "valid_from <= valid_to",
            name="ck_google_ads_m5_valid_dates",
        ),
        sa.CheckConstraint(
            "approval_status = 'APPROVED_PROVISIONAL_XLSX'",
            name="ck_google_ads_m5_provisional",
        ),
        sa.CheckConstraint(
            "length(btrim(approval_reference)) > 0",
            name="ck_google_ads_m5_approval_ref",
        ),
    )
    op.create_index(
        "ix_google_ads_m5_branch_dates", TABLE,
        ["sucursal_canon", "valid_from", "valid_to"],
    )
    op.create_index(
        "ix_google_ads_m5_customer_dates", TABLE,
        ["customer_id", "valid_from", "valid_to"],
    )


def downgrade():
    # Never silently discard manually approved mappings on rollback.
    bind = op.get_bind()
    count = bind.execute(
        sa.text("SELECT COUNT(*) FROM google_ads_branch_identity_mappings")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "M5 rollback bloqueado: existen identidades aprobadas; "
            "se requiere revisión explícita de los datos."
        )
    op.drop_index(
        "ix_google_ads_m5_customer_dates", table_name=TABLE,
    )
    op.drop_index(
        "ix_google_ads_m5_branch_dates", table_name=TABLE,
    )
    op.drop_table(TABLE)
