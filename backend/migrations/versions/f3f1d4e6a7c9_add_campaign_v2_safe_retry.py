"""add Campaign V2 safe retry audit

Revision ID: f3f1d4e6a7c9
Revises: f3e0c3d5a6b8
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "f3f1d4e6a7c9"
down_revision = "f3e0c3d5a6b8"
branch_labels = None
depends_on = None


TABLE = "marketing_campaign_v2_provider_campaigns"
STATUS_CONSTRAINT = "ck_marketing_campaign_v2_provider_campaign_status"
RETRY_ELIGIBLE_CONSTRAINT = "ck_mkt_v2_provider_campaign_retry_eligible"
RETRY_EXHAUSTED_CONSTRAINT = "ck_mkt_v2_provider_campaign_retry_exhausted"
RETRY_ATTEMPTS_CONSTRAINT = "ck_mkt_v2_provider_campaign_retry_attempts"
RETRY_LAST_USER_FK = "fk_mkt_v2_provider_campaign_retry_last_user"
RETRY_NEXT_INDEX = "ix_mkt_v2_provider_campaign_retry_next"


def upgrade():
    op.add_column(
        TABLE,
        sa.Column(
            "retry_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "retry_last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "retry_next_allowed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "retry_last_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "retry_history_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    op.create_foreign_key(
        RETRY_LAST_USER_FK,
        TABLE,
        "users",
        ["retry_last_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        RETRY_NEXT_INDEX,
        TABLE,
        ["retry_next_allowed_at"],
        unique=False,
    )

    op.drop_constraint(
        RETRY_ELIGIBLE_CONSTRAINT,
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
        "'SUBMITTED', 'SCHEDULED', 'RETRY_ELIGIBLE', "
        "'RETRY_EXHAUSTED', 'PROVIDER_ERROR', "
        "'RECONCILIATION_REQUIRED'"
        ")",
    )
    op.create_check_constraint(
        RETRY_ATTEMPTS_CONSTRAINT,
        TABLE,
        "retry_attempt_count >= 0 AND retry_attempt_count <= 3",
    )
    op.create_check_constraint(
        RETRY_ELIGIBLE_CONSTRAINT,
        TABLE,
        "status <> 'RETRY_ELIGIBLE' OR ("
        "reconciliation_resolution = 'NOT_CREATED_CONFIRMED' "
        "AND provider_campaign_id IS NULL "
        "AND retry_attempt_count < 3"
        ")",
    )
    op.create_check_constraint(
        RETRY_EXHAUSTED_CONSTRAINT,
        TABLE,
        "status <> 'RETRY_EXHAUSTED' OR ("
        "reconciliation_resolution = 'NOT_CREATED_CONFIRMED' "
        "AND provider_campaign_id IS NULL "
        "AND retry_attempt_count >= 3"
        ")",
    )


def downgrade():
    bind = op.get_bind()
    retry_audit_count = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {TABLE} "
            "WHERE retry_attempt_count > 0 "
            "OR retry_last_attempt_at IS NOT NULL "
            "OR retry_next_allowed_at IS NOT NULL "
            "OR retry_last_by_user_id IS NOT NULL "
            "OR status = 'RETRY_EXHAUSTED'"
        )
    ).scalar_one()
    if int(retry_audit_count or 0) > 0:
        raise RuntimeError(
            "Cannot downgrade Campaign V2 safe retry while retry audit "
            "data exists."
        )

    op.drop_constraint(
        RETRY_EXHAUSTED_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        RETRY_ELIGIBLE_CONSTRAINT,
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        RETRY_ATTEMPTS_CONSTRAINT,
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
        "'SUBMITTED', 'SCHEDULED', 'RETRY_ELIGIBLE', "
        "'PROVIDER_ERROR', 'RECONCILIATION_REQUIRED'"
        ")",
    )
    op.create_check_constraint(
        RETRY_ELIGIBLE_CONSTRAINT,
        TABLE,
        "status <> 'RETRY_ELIGIBLE' OR ("
        "reconciliation_resolution = 'NOT_CREATED_CONFIRMED' "
        "AND provider_campaign_id IS NULL"
        ")",
    )

    op.drop_index(RETRY_NEXT_INDEX, table_name=TABLE)
    op.drop_constraint(
        RETRY_LAST_USER_FK,
        TABLE,
        type_="foreignkey",
    )
    op.drop_column(TABLE, "retry_history_json")
    op.drop_column(TABLE, "retry_last_by_user_id")
    op.drop_column(TABLE, "retry_next_allowed_at")
    op.drop_column(TABLE, "retry_last_attempt_at")
    op.drop_column(TABLE, "retry_attempt_count")
