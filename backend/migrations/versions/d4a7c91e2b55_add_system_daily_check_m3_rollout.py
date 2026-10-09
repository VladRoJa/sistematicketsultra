"""add system daily check m3 rollout branches

Revision ID: d4a7c91e2b55
Revises: a9d2f6c7b108
Create Date: 2026-10-09
"""

from alembic import op
import sqlalchemy as sa


revision = "d4a7c91e2b55"
down_revision = "a9d2f6c7b108"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_daily_check_rollout_branches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("enabled_from", sa.Date(), nullable=False),
        sa.Column("disabled_from", sa.Date(), nullable=True),
        sa.Column("configured_by_user_id", sa.Integer(), nullable=False),
        sa.Column("disabled_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "disabled_from IS NULL OR disabled_from >= enabled_from",
            name="ck_system_daily_check_rollout_date_order",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            name="fk_system_daily_check_rollout_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["configured_by_user_id"],
            ["users.id"],
            name="fk_system_daily_check_rollout_configured_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["disabled_by_user_id"],
            ["users.id"],
            name="fk_system_daily_check_rollout_disabled_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_system_daily_check_rollout_branches",
        ),
        sa.UniqueConstraint(
            "sucursal_id",
            "enabled_from",
            name="uq_system_daily_check_rollout_branch_start",
        ),
    )
    op.create_index(
        "ix_system_daily_check_rollout_effective_dates",
        "system_daily_check_rollout_branches",
        ["enabled_from", "disabled_from"],
        unique=False,
    )
    op.create_index(
        "ix_system_daily_check_rollout_branch_dates",
        "system_daily_check_rollout_branches",
        ["sucursal_id", "enabled_from", "disabled_from"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_system_daily_check_rollout_branch_dates",
        table_name="system_daily_check_rollout_branches",
    )
    op.drop_index(
        "ix_system_daily_check_rollout_effective_dates",
        table_name="system_daily_check_rollout_branches",
    )
    op.drop_table("system_daily_check_rollout_branches")
