"""add Campaign V2 provider reconciliation audit

Revision ID: f3e0c3d5a6b8
Revises: f3d9b2c4e5f7
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "f3e0c3d5a6b8"
down_revision = "f3d9b2c4e5f7"
branch_labels = None
depends_on = None


TABLE = "marketing_campaign_v2_provider_campaigns"
STATUS_CONSTRAINT = "ck_marketing_campaign_v2_provider_campaign_status"
RESOLUTION_CONSTRAINT = (
    "ck_mkt_v2_provider_campaign_reconciliation_resolution"
)
AUDIT_CONSTRAINT = "ck_mkt_v2_provider_campaign_reconciliation_audit"
FOUND_CONSTRAINT = "ck_mkt_v2_provider_campaign_reconciled_found"
RETRY_CONSTRAINT = "ck_mkt_v2_provider_campaign_retry_eligible"
RECONCILED_BY_FK = "fk_mkt_v2_provider_campaign_reconciled_by_user"


def upgrade():
    op.add_column(
        TABLE,
        sa.Column(
            "reconciliation_resolution",
            sa.String(length=40),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column("reconciliation_note", sa.Text(), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "reconciliation_snapshot_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        TABLE,
        sa.Column("reconciled_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "reconciled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        RECONCILED_BY_FK,
        TABLE,
        "users",
        ["reconciled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        STATUS_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.create_check_constraint(
        STATUS_CONSTRAINT,
        TABLE,
        "status IN ("
        "'PREPARED', 'READY', 'BLOCKED', 'SUBMITTING', "
        "'SUBMITTED', 'SCHEDULED', 'RETRY_ELIGIBLE', "
        "'PROVIDER_ERROR', 'RECONCILIATION_REQUIRED'"
        ")",
    )
    op.create_check_constraint(
        RESOLUTION_CONSTRAINT,
        TABLE,
        "reconciliation_resolution IS NULL OR "
        "reconciliation_resolution IN ("
        "'PROVIDER_CAMPAIGN_FOUND', 'NOT_CREATED_CONFIRMED'"
        ")",
    )
    op.create_check_constraint(
        AUDIT_CONSTRAINT,
        TABLE,
        "("
        "reconciliation_resolution IS NULL "
        "AND reconciled_at IS NULL "
        "AND reconciliation_note IS NULL"
        ") OR ("
        "reconciliation_resolution IS NOT NULL "
        "AND reconciled_at IS NOT NULL "
        "AND reconciliation_note IS NOT NULL "
        "AND length(trim(reconciliation_note)) > 0"
        ")",
    )
    op.create_check_constraint(
        FOUND_CONSTRAINT,
        TABLE,
        "reconciliation_resolution <> 'PROVIDER_CAMPAIGN_FOUND' "
        "OR provider_campaign_id IS NOT NULL",
    )
    op.create_check_constraint(
        RETRY_CONSTRAINT,
        TABLE,
        "status <> 'RETRY_ELIGIBLE' OR ("
        "reconciliation_resolution = 'NOT_CREATED_CONFIRMED' "
        "AND provider_campaign_id IS NULL"
        ")",
    )


def downgrade():
    bind = op.get_bind()
    reconciliation_count = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {TABLE} "
            "WHERE reconciliation_resolution IS NOT NULL "
            "OR reconciliation_note IS NOT NULL "
            "OR reconciled_at IS NOT NULL "
            "OR status = 'RETRY_ELIGIBLE'"
        )
    ).scalar_one()
    if int(reconciliation_count or 0) > 0:
        raise RuntimeError(
            "Cannot downgrade Campaign V2 reconciliation while audit "
            "data exists."
        )

    op.drop_constraint(
        RETRY_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        FOUND_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        AUDIT_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        RESOLUTION_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        STATUS_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.create_check_constraint(
        STATUS_CONSTRAINT,
        TABLE,
        "status IN ("
        "'PREPARED', 'READY', 'BLOCKED', 'SUBMITTING', "
        "'SUBMITTED', 'SCHEDULED', 'PROVIDER_ERROR', "
        "'RECONCILIATION_REQUIRED'"
        ")",
    )

    op.drop_constraint(
        RECONCILED_BY_FK,
        TABLE,
        type_="foreignkey",
    )
    op.drop_column(TABLE, "reconciled_at")
    op.drop_column(TABLE, "reconciled_by_user_id")
    op.drop_column(TABLE, "reconciliation_snapshot_json")
    op.drop_column(TABLE, "reconciliation_note")
    op.drop_column(TABLE, "reconciliation_resolution")
