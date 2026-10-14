"""M6 candidate correction evidence only; no replacement or publication.

Revision ID: e8b2c41d7a60
Revises: c9e1a4d6b720

Creates isolated fact snapshots keyed by correction case. Existing M5/M6
fact tables, Warehouse RAW, Funnel queries and canonical rows are untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = "e8b2c41d7a60"
down_revision = "c9e1a4d6b720"
branch_labels = None
depends_on = None

CASE = "google_ads_m6_correction_cases"
CAMPAIGN = "google_ads_m6_correction_campaign_facts"
GROUP = "google_ads_m6_correction_group_facts"


def upgrade():
    op.create_table(
        CASE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.String(10), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("expected_publication_id", sa.BigInteger(), nullable=True),
        sa.Column("campaign_upload_id", sa.Integer(), nullable=False),
        sa.Column("ad_group_upload_id", sa.Integer(), nullable=False),
        sa.Column("approval_version_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_sha256", sa.String(64), nullable=False),
        sa.Column("ad_group_sha256", sa.String(64), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["expected_publication_id"],
                                ["google_ads_m6_daily_publications.id"],
                                name="fk_ga_m6_corr_prior", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["campaign_upload_id"], ["warehouse_uploads.id"],
                                name="fk_ga_m6_corr_campaign_upload", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ad_group_upload_id"], ["warehouse_uploads.id"],
                                name="fk_ga_m6_corr_group_upload", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_version_id"],
                                ["google_ads_branch_approval_versions.id"],
                                name="fk_ga_m6_corr_approval", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"],
                                name="fk_ga_m6_corr_actor", ondelete="RESTRICT"),
        sa.UniqueConstraint("customer_id", "business_date", "revision",
                            name="uq_ga_m6_corr_case_revision"),
        sa.CheckConstraint("customer_id ~ '^[0-9]{10}$'",
                           name="ck_ga_m6_corr_customer"),
        sa.CheckConstraint("business_date >= DATE '2026-10-13'",
                           name="ck_ga_m6_corr_date"),
        sa.CheckConstraint("revision > 0", name="ck_ga_m6_corr_revision"),
        sa.CheckConstraint("revision = 1 OR expected_publication_id IS NOT NULL",
                           name="ck_ga_m6_corr_prior_revision"),
        sa.CheckConstraint("campaign_upload_id <> ad_group_upload_id",
                           name="ck_ga_m6_corr_sources"),
        sa.CheckConstraint("campaign_sha256 ~ '^[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_campaign_sha"),
        sa.CheckConstraint("ad_group_sha256 ~ '^[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_group_sha"),
        sa.CheckConstraint("length(btrim(reason)) > 0",
                           name="ck_ga_m6_corr_reason"),
    )
    op.create_index("ix_ga_m6_corr_customer_day", CASE,
                    ["customer_id", "business_date"])

    common_metrics = lambda: [
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False),
        sa.Column("clicks", sa.BigInteger(), nullable=False),
        sa.Column("conversions", sa.Numeric(18, 4), nullable=False),
        sa.Column("conversion_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    ]
    op.create_table(
        CAMPAIGN,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_key", sa.String(80), nullable=False),
        sa.Column("campaign_name", sa.String(255), nullable=False),
        *common_metrics(),
        sa.ForeignKeyConstraint(["case_id"], [CASE + ".id"],
                                name="fk_ga_m6_corr_campaign_case", ondelete="RESTRICT"),
        sa.UniqueConstraint("case_id", "campaign_key",
                            name="uq_ga_m6_corr_campaign_key"),
        sa.CheckConstraint("campaign_key ~ '^name:[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_campaign_key"),
        sa.CheckConstraint("currency_code = 'MXN'",
                           name="ck_ga_m6_corr_campaign_currency"),
        sa.CheckConstraint(
            "cost >= 0 AND impressions >= 0 AND clicks >= 0 AND "
            "conversions >= 0 AND conversion_value >= 0",
            name="ck_ga_m6_corr_campaign_metrics",
        ),
    )
    op.create_index("ix_ga_m6_corr_campaign_case", CAMPAIGN, ["case_id"])

    op.create_table(
        GROUP,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_key", sa.String(80), nullable=False),
        sa.Column("ad_group_key", sa.String(80), nullable=False),
        sa.Column("campaign_name", sa.String(255), nullable=False),
        sa.Column("ad_group_name", sa.String(255), nullable=False),
        *common_metrics()[:-1],
        sa.Column("free_pass_conversions", sa.Numeric(18, 4), nullable=False),
        sa.Column("web_purchase_conversions", sa.Numeric(18, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["case_id"], [CASE + ".id"],
                                name="fk_ga_m6_corr_group_case", ondelete="RESTRICT"),
        sa.UniqueConstraint("case_id", "campaign_key", "ad_group_key",
                            name="uq_ga_m6_corr_group_key"),
        sa.CheckConstraint("campaign_key ~ '^name:[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_group_campaign_key"),
        sa.CheckConstraint("ad_group_key ~ '^name:[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_group_key"),
        sa.CheckConstraint("currency_code = 'MXN'",
                           name="ck_ga_m6_corr_group_currency"),
        sa.CheckConstraint(
            "cost >= 0 AND impressions >= 0 AND clicks >= 0 AND "
            "conversions >= 0 AND free_pass_conversions >= 0 AND "
            "web_purchase_conversions >= 0 AND conversion_value >= 0",
            name="ck_ga_m6_corr_group_metrics",
        ),
    )
    op.create_index("ix_ga_m6_corr_group_case", GROUP, ["case_id"])


def downgrade():
    conn = op.get_bind()
    for table in (GROUP, CAMPAIGN, CASE):
        if conn.execute(sa.text("SELECT EXISTS(SELECT 1 FROM " + table + ")")).scalar():
            raise RuntimeError("M6 correction rollback blocked: candidate evidence exists")
    op.drop_index("ix_ga_m6_corr_group_case", table_name=GROUP)
    op.drop_table(GROUP)
    op.drop_index("ix_ga_m6_corr_campaign_case", table_name=CAMPAIGN)
    op.drop_table(CAMPAIGN)
    op.drop_index("ix_ga_m6_corr_customer_day", table_name=CASE)
    op.drop_table(CASE)
