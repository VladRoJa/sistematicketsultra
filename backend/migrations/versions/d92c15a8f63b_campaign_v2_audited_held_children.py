"""Add durable, audited HELD state for Campaign V2 provider children.

Revision ID: d92c15a8f63b
Revises: c29f6a8d1e70
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

revision = "d92c15a8f63b"
down_revision = "c29f6a8d1e70"
branch_labels = None
depends_on = None

TABLE = "marketing_campaign_v2_provider_campaigns"
STATUS_CONSTRAINT = "ck_marketing_campaign_v2_provider_campaign_status"
AUDIT_CONSTRAINT = "ck_mkt_v2_provider_hold_audit_complete"
HELD_CONSTRAINT = "ck_mkt_v2_provider_held_unattempted"
FK = "fk_mkt_v2_provider_held_by_user"


def _create_status_constraint(*, include_held: bool) -> None:
    statuses = (
        "'PREPARED', 'READY', 'BLOCKED', "
        + ("'HELD', " if include_held else "")
        + "'SUBMITTING', 'SUBMITTED', 'SCHEDULED', "
        "'RETRY_ELIGIBLE', 'RETRY_EXHAUSTED', 'PROVIDER_ERROR', "
        "'RECONCILIATION_REQUIRED'"
    )
    op.create_check_constraint(
        STATUS_CONSTRAINT, TABLE, "status IN (" + statuses + ")",
    )


def upgrade():
    op.add_column(TABLE, sa.Column("hold_reason", sa.String(80), nullable=True))
    op.add_column(TABLE, sa.Column("held_by_user_id", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("held_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "hold_evidence_json", sa.JSON(), nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_foreign_key(
        FK, TABLE, "users", ["held_by_user_id"], ["id"], ondelete="RESTRICT",
    )
    op.drop_constraint(STATUS_CONSTRAINT, TABLE, type_="check")
    _create_status_constraint(include_held=True)
    op.create_check_constraint(
        AUDIT_CONSTRAINT, TABLE,
        "(hold_reason IS NULL AND held_by_user_id IS NULL AND held_at IS NULL)"
        " OR (hold_reason IS NOT NULL AND held_by_user_id IS NOT NULL AND held_at IS NOT NULL)",
    )
    op.create_check_constraint(
        HELD_CONSTRAINT, TABLE,
        "status <> 'HELD' OR ("
        "hold_reason = 'CHANNEL_DAILY_QUOTA' "
        "AND hold_reason IS NOT NULL "
        "AND held_by_user_id IS NOT NULL "
        "AND held_at IS NOT NULL "
        "AND provider_campaign_id IS NULL "
        "AND submit_started_at IS NULL "
        "AND submitted_at IS NULL"
        ")",
    )


def downgrade():
    count = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM " + TABLE + " WHERE "
        "status = 'HELD' OR hold_reason IS NOT NULL OR held_at IS NOT NULL "
        "OR held_by_user_id IS NOT NULL"
    )).scalar()
    if int(count or 0) > 0:
        raise RuntimeError(
            "No se puede revertir: existen lotes HELD o historial de retencion."
        )
    op.drop_constraint(HELD_CONSTRAINT, TABLE, type_="check")
    op.drop_constraint(AUDIT_CONSTRAINT, TABLE, type_="check")
    op.drop_constraint(STATUS_CONSTRAINT, TABLE, type_="check")
    _create_status_constraint(include_held=False)
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.drop_column(TABLE, "hold_evidence_json")
    op.drop_column(TABLE, "held_at")
    op.drop_column(TABLE, "held_by_user_id")
    op.drop_column(TABLE, "hold_reason")
