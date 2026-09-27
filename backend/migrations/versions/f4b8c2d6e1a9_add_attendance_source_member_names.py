"""add attendance source member names

Revision ID: f4b8c2d6e1a9
Revises: d1a7f3c9e5b2
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa


revision = "f4b8c2d6e1a9"
down_revision = "d1a7f3c9e5b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "warehouse_attendance_visits",
        sa.Column(
            "source_first_name",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "warehouse_attendance_visits",
        sa.Column(
            "source_last_name",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column(
        "warehouse_attendance_visits",
        "source_last_name",
    )
    op.drop_column(
        "warehouse_attendance_visits",
        "source_first_name",
    )
