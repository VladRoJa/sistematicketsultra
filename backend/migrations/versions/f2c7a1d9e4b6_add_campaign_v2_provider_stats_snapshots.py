"""add Campaign V2 provider stats snapshots

Revision ID: f2c7a1d9e4b6
Revises: d3e7f1a9c2b4
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f2c7a1d9e4b6"
down_revision = "d3e7f1a9c2b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaign_v2_provider_stats_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("campaign_v2_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_campaign_id", sa.String(length=255), nullable=False),
        sa.Column("analytics_status", sa.String(length=50), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_successful", sa.Integer(), nullable=False),
        sa.Column("raw_failed", sa.Integer(), nullable=False),
        sa.Column("raw_sent", sa.Integer(), nullable=False),
        sa.Column("raw_delivered", sa.Integer(), nullable=False),
        sa.Column("raw_viewed", sa.Integer(), nullable=False),
        sa.Column("raw_answered", sa.Integer(), nullable=False),
        sa.Column("raw_interaction_groups", sa.Integer(), nullable=False),
        sa.Column("raw_interaction_items", sa.Integer(), nullable=False),
        sa.Column("analytics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "button_interactions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("provider_recipient_count", sa.Integer(), nullable=False),
        sa.Column("matched_recipient_count", sa.Integer(), nullable=False),
        sa.Column("unmatched_provider_count", sa.Integer(), nullable=False),
        sa.Column(
            "frozen_recipient_without_provider_status_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(fingerprint) = 64",
            name="ck_marketing_campaign_v2_provider_stats_fingerprint_length",
        ),
        sa.CheckConstraint(
            "raw_successful >= 0 AND raw_failed >= 0 AND raw_sent >= 0 "
            "AND raw_delivered >= 0 AND raw_viewed >= 0 AND raw_answered >= 0 "
            "AND raw_interaction_groups >= 0 AND raw_interaction_items >= 0",
            name="ck_marketing_campaign_v2_provider_stats_raw_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "provider_recipient_count >= 0 AND matched_recipient_count >= 0 "
            "AND unmatched_provider_count >= 0 "
            "AND frozen_recipient_without_provider_status_count >= 0",
            name="ck_marketing_campaign_v2_provider_stats_diagnostics_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_v2_id"],
            ["marketing_campaign_v2_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_v2_id",
            "provider",
            "provider_campaign_id",
            "fingerprint",
            name="uq_marketing_campaign_v2_provider_stats_snapshot_identity",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_provider_stats_campaign_fetched",
        "marketing_campaign_v2_provider_stats_snapshots",
        ["campaign_v2_id", "fetched_at"],
        unique=False,
    )

    op.create_table(
        "marketing_campaign_v2_provider_recipient_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("normalized_phone", sa.String(length=128), nullable=False),
        sa.Column("campaign_recipient_id", sa.BigInteger(), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("delivery_bucket", sa.String(length=20), nullable=True),
        sa.Column(
            "button_labels_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('SUCCESSFUL', 'FAILED')",
            name="ck_marketing_campaign_v2_provider_obs_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'FAILED' AND delivery_bucket IS NULL) OR "
            "(outcome = 'SUCCESSFUL' AND delivery_bucket IN "
            "('SENT', 'DELIVERED', 'VIEWED'))",
            name="ck_marketing_campaign_v2_provider_obs_delivery",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_recipient_id"],
            ["marketing_campaign_v2_recipients.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["marketing_campaign_v2_provider_stats_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "normalized_phone",
            name="uq_marketing_campaign_v2_provider_obs_snapshot_phone",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_provider_obs_snapshot_id",
        "marketing_campaign_v2_provider_recipient_observations",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_provider_obs_campaign_recipient_id",
        "marketing_campaign_v2_provider_recipient_observations",
        ["campaign_recipient_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign_v2_provider_obs_normalized_phone",
        "marketing_campaign_v2_provider_recipient_observations",
        ["normalized_phone"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_campaign_v2_provider_obs_normalized_phone",
        table_name="marketing_campaign_v2_provider_recipient_observations",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_provider_obs_campaign_recipient_id",
        table_name="marketing_campaign_v2_provider_recipient_observations",
    )
    op.drop_index(
        "ix_marketing_campaign_v2_provider_obs_snapshot_id",
        table_name="marketing_campaign_v2_provider_recipient_observations",
    )
    op.drop_table("marketing_campaign_v2_provider_recipient_observations")
    op.drop_index(
        "ix_marketing_campaign_v2_provider_stats_campaign_fetched",
        table_name="marketing_campaign_v2_provider_stats_snapshots",
    )
    op.drop_table("marketing_campaign_v2_provider_stats_snapshots")
