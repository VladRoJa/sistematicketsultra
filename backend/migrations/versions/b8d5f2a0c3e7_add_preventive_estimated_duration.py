"""add preventive estimated duration

Revision ID: b8d5f2a0c3e7
Revises: a7c4e1f9b2d6
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa


revision = "b8d5f2a0c3e7"
down_revision = "a7c4e1f9b2d6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "maintenance_preventive_schedules",
        sa.Column(
            "estimated_duration_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_maintenance_preventive_schedules_estimated_duration",
        "maintenance_preventive_schedules",
        "estimated_duration_minutes IS NULL "
        "OR estimated_duration_minutes > 0",
    )

    op.add_column(
        "maintenance_preventive_items",
        sa.Column(
            "estimated_duration_minutes_input",
            sa.String(length=20),
            nullable=True,
        ),
    )
    op.add_column(
        "maintenance_preventive_items",
        sa.Column(
            "estimated_duration_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_maintenance_preventive_items_estimated_duration",
        "maintenance_preventive_items",
        "estimated_duration_minutes IS NULL "
        "OR estimated_duration_minutes > 0",
    )

    op.add_column(
        "tickets",
        sa.Column(
            "maintenance_estimated_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_tickets_maintenance_estimated_minutes",
        "tickets",
        "maintenance_estimated_minutes IS NULL "
        "OR maintenance_estimated_minutes > 0",
    )


def downgrade():
    op.drop_constraint(
        "ck_tickets_maintenance_estimated_minutes",
        "tickets",
        type_="check",
    )
    op.drop_column("tickets", "maintenance_estimated_minutes")

    op.drop_constraint(
        "ck_maintenance_preventive_items_estimated_duration",
        "maintenance_preventive_items",
        type_="check",
    )
    op.drop_column(
        "maintenance_preventive_items",
        "estimated_duration_minutes",
    )
    op.drop_column(
        "maintenance_preventive_items",
        "estimated_duration_minutes_input",
    )

    op.drop_constraint(
        "ck_maintenance_preventive_schedules_estimated_duration",
        "maintenance_preventive_schedules",
        type_="check",
    )
    op.drop_column(
        "maintenance_preventive_schedules",
        "estimated_duration_minutes",
    )
