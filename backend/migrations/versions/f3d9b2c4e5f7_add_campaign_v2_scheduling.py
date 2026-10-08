"""add Campaign V2 scheduled dispatch audit

Revision ID: f3d9b2c4e5f7
Revises: f3c8a1b2d4e6
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "f3d9b2c4e5f7"
down_revision = "f3c8a1b2d4e6"
branch_labels = None
depends_on = None


TABLE = "marketing_campaign_v2_provider_campaigns"
STATUS_CONSTRAINT = "ck_marketing_campaign_v2_provider_campaign_status"
SCHEDULE_CONSTRAINT = (
    "ck_marketing_campaign_v2_provider_campaign_schedule_complete"
)
SCHEDULED_INDEX = (
    "ix_marketing_campaign_v2_provider_campaign_scheduled_for"
)
SCHEDULED_BY_FK = (
    "fk_marketing_campaign_v2_provider_campaign_scheduled_by_user_id_users"
)


def upgrade():
    op.add_column(
        TABLE,
        sa.Column("scheduled_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column("scheduled_timezone", sa.String(length=100), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "scheduled_local_at",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "scheduled_for",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column("provider_send_at", sa.String(length=64), nullable=True),
    )

    op.create_foreign_key(
        SCHEDULED_BY_FK,
        TABLE,
        "users",
        ["scheduled_by_user_id"],
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
        "'SUBMITTED', 'SCHEDULED', 'PROVIDER_ERROR', "
        "'RECONCILIATION_REQUIRED'"
        ")",
    )
    op.create_check_constraint(
        SCHEDULE_CONSTRAINT,
        TABLE,
        "("
        "scheduled_timezone IS NULL AND scheduled_local_at IS NULL "
        "AND scheduled_for IS NULL AND provider_send_at IS NULL"
        ") OR ("
        "scheduled_timezone IS NOT NULL AND scheduled_local_at IS NOT NULL "
        "AND scheduled_for IS NOT NULL AND provider_send_at IS NOT NULL"
        ")",
    )
    op.create_index(
        SCHEDULED_INDEX,
        TABLE,
        ["scheduled_for"],
        unique=False,
    )


def downgrade():
    bind = op.get_bind()
    scheduled_count = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {TABLE} "
            "WHERE scheduled_timezone IS NOT NULL "
            "OR scheduled_local_at IS NOT NULL "
            "OR scheduled_for IS NOT NULL "
            "OR provider_send_at IS NOT NULL"
        )
    ).scalar_one()
    if int(scheduled_count or 0) > 0:
        raise RuntimeError(
            "Cannot downgrade Campaign V2 scheduling while scheduling "
            "audit data exists."
        )

    op.drop_index(
        SCHEDULED_INDEX,
        table_name=TABLE,
    )
    op.drop_constraint(
        SCHEDULE_CONSTRAINT,
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
        "'SUBMITTED', 'PROVIDER_ERROR', 'RECONCILIATION_REQUIRED'"
        ")",
    )

    op.drop_constraint(
        SCHEDULED_BY_FK,
        TABLE,
        type_="foreignkey",
    )
    op.drop_column(TABLE, "provider_send_at")
    op.drop_column(TABLE, "scheduled_for")
    op.drop_column(TABLE, "scheduled_local_at")
    op.drop_column(TABLE, "scheduled_timezone")
    op.drop_column(TABLE, "scheduled_by_user_id")
