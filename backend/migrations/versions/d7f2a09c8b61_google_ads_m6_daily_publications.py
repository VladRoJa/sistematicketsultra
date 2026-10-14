"""Versioned M6 daily canonical publications; schema only, no auto-publish.

Revision ID: d7f2a09c8b61
Revises: b3e7c2d9a104
"""
from alembic import op
import sqlalchemy as sa

revision = "d7f2a09c8b61"
down_revision = "b3e7c2d9a104"
branch_labels = None
depends_on = None

TABLE = "google_ads_m6_daily_publications"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.String(10), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("campaign_upload_id", sa.Integer(), nullable=False),
        sa.Column("ad_group_upload_id", sa.Integer(), nullable=False),
        sa.Column("approval_version_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_sha256", sa.String(64), nullable=False),
        sa.Column("ad_group_sha256", sa.String(64), nullable=False),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_by_user_id", sa.Integer(), nullable=False),
        sa.Column("published_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["campaign_upload_id"], ["warehouse_uploads.id"],
                                name="fk_ga_m6_pub_campaign", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ad_group_upload_id"], ["warehouse_uploads.id"],
                                name="fk_ga_m6_pub_group", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_version_id"],
                                ["google_ads_branch_approval_versions.id"],
                                name="fk_ga_m6_pub_approval", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"],
                                name="fk_ga_m6_pub_actor", ondelete="RESTRICT"),
        sa.UniqueConstraint("customer_id", "business_date", "revision",
                            name="uq_ga_m6_pub_revision"),
        sa.CheckConstraint("customer_id ~ '^[0-9]{10}$'",
                           name="ck_ga_m6_pub_customer"),
        sa.CheckConstraint("business_date >= DATE '2026-10-13'",
                           name="ck_ga_m6_pub_first_day"),
        sa.CheckConstraint("revision > 0", name="ck_ga_m6_pub_revision"),
        sa.CheckConstraint("campaign_upload_id <> ad_group_upload_id",
                           name="ck_ga_m6_pub_distinct_sources"),
        sa.CheckConstraint("campaign_sha256 ~ '^[a-f0-9]{64}$'",
                           name="ck_ga_m6_pub_campaign_sha"),
        sa.CheckConstraint("ad_group_sha256 ~ '^[a-f0-9]{64}$'",
                           name="ck_ga_m6_pub_group_sha"),
    )
    op.create_index(
        "uq_ga_m6_pub_canonical_day", TABLE,
        ["customer_id", "business_date"], unique=True,
        postgresql_where=sa.text("is_canonical"),
    )
    op.create_index(
        "ix_ga_m6_pub_sources", TABLE,
        ["campaign_upload_id", "ad_group_upload_id"],
    )


def downgrade():
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM " + TABLE)).scalar_one()
    if count:
        raise RuntimeError("M6 publication rollback blocked: history requires review")
    op.drop_index("ix_ga_m6_pub_sources", table_name=TABLE)
    op.drop_index("uq_ga_m6_pub_canonical_day", table_name=TABLE)
    op.drop_table(TABLE)
