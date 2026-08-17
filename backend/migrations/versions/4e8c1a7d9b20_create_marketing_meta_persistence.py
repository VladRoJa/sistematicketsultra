"""create marketing meta persistence tables

Revision ID: 4e8c1a7d9b20
Revises: d3a4f71c9b82
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "4e8c1a7d9b20"
down_revision = "d3a4f71c9b82"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_meta_sync_runs",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "period_key",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "accounts_requested",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "accounts_completed",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "accounts_failed",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "pages_received",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "insights_received",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "insights_unique",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "is_canonical",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "date_from <= date_to",
            name="ck_marketing_meta_sync_runs_date_range",
        ),
        sa.CheckConstraint(
            "status IN "
            "('RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED')",
            name="ck_marketing_meta_sync_runs_status",
        ),
        sa.CheckConstraint(
            "accounts_requested >= 0 "
            "AND accounts_completed >= 0 "
            "AND accounts_failed >= 0 "
            "AND pages_received >= 0 "
            "AND insights_received >= 0 "
            "AND insights_unique >= 0",
            name="ck_marketing_meta_sync_runs_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "NOT is_canonical "
            "OR (status = 'COMPLETED' AND accounts_failed = 0)",
            name="ck_marketing_meta_sync_runs_canonical_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_marketing_meta_sync_runs_period_key",
        "marketing_meta_sync_runs",
        ["period_key"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_meta_sync_runs_status",
        "marketing_meta_sync_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_meta_sync_runs_is_canonical",
        "marketing_meta_sync_runs",
        ["is_canonical"],
        unique=False,
    )
    op.create_index(
        "uq_marketing_meta_sync_runs_canonical_period",
        "marketing_meta_sync_runs",
        ["period_key"],
        unique=True,
        postgresql_where=sa.text("is_canonical = true"),
    )

    op.create_table(
        "marketing_meta_raw_pages",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "sync_run_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "page_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("request_cursor", sa.Text(), nullable=True),
        sa.Column("next_cursor", sa.Text(), nullable=True),
        sa.Column("has_more", sa.Boolean(), nullable=True),
        sa.Column("rows_count", sa.Integer(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "page_number >= 1",
            name="ck_marketing_meta_raw_pages_page_positive",
        ),
        sa.CheckConstraint(
            "rows_count IS NULL OR rows_count >= 0",
            name="ck_marketing_meta_raw_pages_rows_nonnegative",
        ),
        sa.CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="ck_marketing_meta_raw_pages_http_status",
        ),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["marketing_meta_sync_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sync_run_id",
            "account_id",
            "page_number",
            name="uq_marketing_meta_raw_pages_run_account_page",
        ),
    )
    op.create_index(
        "ix_marketing_meta_raw_pages_sync_run_id",
        "marketing_meta_raw_pages",
        ["sync_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_meta_raw_pages_account_id",
        "marketing_meta_raw_pages",
        ["account_id"],
        unique=False,
    )

    op.create_table(
        "marketing_meta_ad_insights",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "sync_run_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "raw_page_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "account_name",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "campaign_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "campaign_name",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "adset_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "adset_name",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "ad_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "ad_name",
            sa.Text(),
            nullable=True,
        ),
        sa.Column("date_start", sa.Date(), nullable=False),
        sa.Column("date_stop", sa.Date(), nullable=False),
        sa.Column(
            "spend",
            sa.Numeric(precision=16, scale=4),
            nullable=False,
        ),
        sa.Column("reach", sa.BigInteger(), nullable=False),
        sa.Column(
            "impressions",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column("clicks", sa.BigInteger(), nullable=False),
        sa.Column("actions_json", sa.JSON(), nullable=False),
        sa.Column(
            "row_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "date_start <= date_stop",
            name="ck_marketing_meta_insights_date_range",
        ),
        sa.CheckConstraint(
            "spend >= 0 "
            "AND reach >= 0 "
            "AND impressions >= 0 "
            "AND clicks >= 0",
            name="ck_marketing_meta_insights_metrics_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["marketing_meta_sync_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_page_id"],
            ["marketing_meta_raw_pages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sync_run_id",
            "account_id",
            "ad_id",
            "date_start",
            "date_stop",
            name="uq_marketing_meta_insights_run_ad_period",
        ),
    )
    for index_name, columns in (
        (
            "ix_marketing_meta_insights_sync_run_id",
            ["sync_run_id"],
        ),
        (
            "ix_marketing_meta_insights_raw_page_id",
            ["raw_page_id"],
        ),
        (
            "ix_marketing_meta_insights_account_id",
            ["account_id"],
        ),
        ("ix_marketing_meta_insights_ad_id", ["ad_id"]),
        (
            "ix_marketing_meta_insights_date_start",
            ["date_start"],
        ),
        (
            "ix_marketing_meta_insights_row_hash",
            ["row_hash"],
        ),
    ):
        op.create_index(
            index_name,
            "marketing_meta_ad_insights",
            columns,
            unique=False,
        )


def downgrade():
    op.drop_table("marketing_meta_ad_insights")
    op.drop_table("marketing_meta_raw_pages")
    op.drop_table("marketing_meta_sync_runs")
