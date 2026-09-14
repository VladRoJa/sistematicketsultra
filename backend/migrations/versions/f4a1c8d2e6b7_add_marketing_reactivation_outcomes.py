"""add marketing reactivation outcomes

Revision ID: f4a1c8d2e6b7
Revises: b7e4d8c2a1f9
Create Date: 2026-09-13 22:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "f4a1c8d2e6b7"
down_revision = "b7e4d8c2a1f9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "marketing_reactivation_campaigns",
        sa.Column(
            "attribution_window_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("14"),
        ),
    )
    op.create_check_constraint(
        "ck_marketing_reactivation_campaigns_attribution_window",
        "marketing_reactivation_campaigns",
        "attribution_window_days BETWEEN 1 AND 90",
    )

    op.create_table(
        "marketing_reactivation_campaign_recipient_outcomes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("campaign_recipient_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reactivated_at_local", sa.DateTime(timezone=False), nullable=True),
        sa.Column("active_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("active_snapshot_row_id", sa.BigInteger(), nullable=True),
        sa.Column("active_id_socio", sa.String(length=64), nullable=True),
        sa.Column("active_sucursal", sa.String(length=255), nullable=True),
        sa.Column("review_reason", sa.String(length=100), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'REACTIVATED', 'REVIEW', 'WINDOW_CLOSED')",
            name="ck_marketing_reactivation_outcomes_status",
        ),
        sa.CheckConstraint(
            "status <> 'REACTIVATED' OR ("
            "reactivated_at_local IS NOT NULL "
            "AND active_snapshot_id IS NOT NULL "
            "AND active_snapshot_row_id IS NOT NULL "
            "AND active_id_socio IS NOT NULL"
            ")",
            name="ck_marketing_reactivation_outcomes_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_recipient_id"],
            ["marketing_reactivation_campaign_recipients.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["active_snapshot_id"],
            ["socios_activos_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["active_snapshot_row_id"],
            ["socios_activos_snapshot_rows.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_recipient_id",
            name="uq_marketing_reactivation_outcomes_recipient",
        ),
    )
    op.create_index(
        "ix_marketing_reactivation_outcomes_status",
        "marketing_reactivation_campaign_recipient_outcomes",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_reactivation_outcomes_active_id_socio",
        "marketing_reactivation_campaign_recipient_outcomes",
        ["active_id_socio"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_marketing_reactivation_outcomes_active_id_socio",
        table_name="marketing_reactivation_campaign_recipient_outcomes",
    )
    op.drop_index(
        "ix_marketing_reactivation_outcomes_status",
        table_name="marketing_reactivation_campaign_recipient_outcomes",
    )
    op.drop_table("marketing_reactivation_campaign_recipient_outcomes")
    op.drop_constraint(
        "ck_marketing_reactivation_campaigns_attribution_window",
        "marketing_reactivation_campaigns",
        type_="check",
    )
    op.drop_column(
        "marketing_reactivation_campaigns",
        "attribution_window_days",
    )
