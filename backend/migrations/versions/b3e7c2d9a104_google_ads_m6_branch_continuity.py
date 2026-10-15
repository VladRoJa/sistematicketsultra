"""M6 Google Ads: versioned branch identity approval schema only.

Revision ID: b3e7c2d9a104
Revises: f62a1b9d4c07
Create Date: 2026-10-13

No M5 table modifications, inserts, approval seeds or Funnel behavior changes.
"""
from alembic import op
import sqlalchemy as sa


revision = "b3e7c2d9a104"
down_revision = "f62a1b9d4c07"
branch_labels = None
depends_on = None

VERSIONS = "google_ads_branch_approval_versions"
IDENTITIES = "google_ads_branch_approved_identities"


def upgrade():
    op.create_table(
        VERSIONS,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.String(10), nullable=False),
        sa.Column("approval_reference", sa.String(255), nullable=False),
        sa.Column("source_approval_reference", sa.String(255), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_campaign_upload_id", sa.Integer(), nullable=False),
        sa.Column("source_ad_group_upload_id", sa.Integer(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=False),
        sa.Column("approved_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_campaign_upload_id"], ["warehouse_uploads.id"],
            name="fk_ga_m6_campaign_source", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_ad_group_upload_id"], ["warehouse_uploads.id"],
            name="fk_ga_m6_group_source", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"],
            name="fk_ga_m6_approved_by", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "customer_id", "approval_reference",
            name="uq_ga_m6_approval_reference",
        ),
        sa.UniqueConstraint(
            "customer_id", "valid_from",
            name="uq_ga_m6_approval_start",
        ),
        sa.CheckConstraint(
            "customer_id ~ '^[0-9]{10}$'",
            name="ck_ga_m6_approval_customer",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from <= valid_to",
            name="ck_ga_m6_approval_dates",
        ),
        sa.CheckConstraint(
            "source_campaign_upload_id <> source_ad_group_upload_id",
            name="ck_ga_m6_distinct_sources",
        ),
        sa.CheckConstraint(
            "length(btrim(approval_reference)) > 0",
            name="ck_ga_m6_approval_reference",
        ),
        sa.CheckConstraint(
            "length(btrim(source_approval_reference)) > 0",
            name="ck_ga_m6_approval_origin",
        ),
    )
    op.create_index(
        "ix_ga_m6_approval_customer_dates", VERSIONS,
        ["customer_id", "valid_from", "valid_to"],
    )
    op.create_table(
        IDENTITIES,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("approval_version_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_key", sa.String(80), nullable=False),
        sa.Column("ad_group_key", sa.String(80), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["approval_version_id"], [VERSIONS + ".id"],
            name="fk_ga_m6_identity_approval", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"], ["track_branch_catalog.sucursal_canon"],
            name="fk_ga_m6_identity_branch", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "approval_version_id", "campaign_key", "ad_group_key",
            name="uq_ga_m6_version_identity",
        ),
        sa.CheckConstraint(
            "campaign_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_ga_m6_campaign_key",
        ),
        sa.CheckConstraint(
            "ad_group_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_ga_m6_ad_group_key",
        ),
    )
    op.create_index(
        "ix_ga_m6_identity_version_branch", IDENTITIES,
        ["approval_version_id", "sucursal_canon"],
    )


def downgrade():
    # Never discard actual approvals without an explicit decision and export.
    conn = op.get_bind()
    for table in (IDENTITIES, VERSIONS):
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM " + table)
        ).scalar_one()
        if count:
            raise RuntimeError(
                "M6 rollback blocked: approved identities/versions exist; "
                "manual review required."
            )
    op.drop_index("ix_ga_m6_identity_version_branch", table_name=IDENTITIES)
    op.drop_table(IDENTITIES)
    op.drop_index("ix_ga_m6_approval_customer_dates", table_name=VERSIONS)
    op.drop_table(VERSIONS)
