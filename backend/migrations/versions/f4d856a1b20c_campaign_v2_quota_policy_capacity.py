"""Append-only operator quota references; no automatic Meta availability.

Revision ID: f4d856a1b20c
Revises: e4b856c9170d
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "f4d856a1b20c"
down_revision = "e4b856c9170d"
branch_labels = None
depends_on = None

POLICY = "marketing_campaign_v2_quota_policy_revisions"
CAPACITY = "marketing_campaign_v2_quota_capacity_attestations"


def upgrade():
    op.create_table(
        POLICY,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_channel_id", sa.String(255), nullable=False),
        sa.Column("portfolio_key", sa.String(128), nullable=False),
        sa.Column("account_key", sa.String(128), nullable=False),
        sa.Column("phone_alias", sa.String(128), nullable=False),
        sa.Column("nominal_channel_limit", sa.Integer(), nullable=True),
        sa.Column("reset_timezone", sa.String(80), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "nominal_channel_limit IS NULL OR nominal_channel_limit > 0",
            name="ck_mkt_v2_quota_nominal_positive",
        ),
        sa.CheckConstraint(
            "length(trim(portfolio_key)) > 0 AND length(trim(account_key)) > 0 "
            "AND length(trim(phone_alias)) > 0 "
            "AND length(trim(reset_timezone)) > 0 "
            "AND length(trim(source_reference)) > 0",
            name="ck_mkt_v2_quota_policy_required",
        ),
        sa.UniqueConstraint("provider_channel_id", "valid_from",
                            name="uq_mkt_v2_quota_channel_revision"),
    )
    op.create_index("ix_mkt_v2_quota_policy_latest", POLICY,
                    ["provider_channel_id", "valid_from"])

    op.create_table(
        CAPACITY,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scope_kind", sa.String(20), nullable=False),
        sa.Column("scope_key", sa.String(255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("remaining_messages", sa.Integer(), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("scope_kind IN ('CHANNEL', 'PORTFOLIO')",
                           name="ck_mkt_v2_quota_capacity_scope"),
        sa.CheckConstraint("remaining_messages >= 0",
                           name="ck_mkt_v2_quota_capacity_nonnegative"),
        sa.CheckConstraint("observed_at < expires_at AND expires_at <= window_ends_at",
                           name="ck_mkt_v2_quota_capacity_window"),
        sa.CheckConstraint(
            "length(trim(scope_key)) > 0 AND length(trim(source_reference)) > 0",
            name="ck_mkt_v2_quota_capacity_evidence",
        ),
        sa.UniqueConstraint("scope_kind", "scope_key", "observed_at",
                            name="uq_mkt_v2_quota_capacity_evidence_time"),
    )
    op.create_index("ix_mkt_v2_quota_capacity_latest", CAPACITY,
                    ["scope_kind", "scope_key", "observed_at"])


def downgrade():
    for name in (CAPACITY, POLICY):
        count = op.get_bind().execute(
            sa.text("SELECT COUNT(*) FROM " + name)
        ).scalar()
        if int(count or 0):
            raise RuntimeError(
                "No se elimina historial de cuotas sin autorización explícita."
            )
    op.drop_index("ix_mkt_v2_quota_capacity_latest", table_name=CAPACITY)
    op.drop_table(CAPACITY)
    op.drop_index("ix_mkt_v2_quota_policy_latest", table_name=POLICY)
    op.drop_table(POLICY)
