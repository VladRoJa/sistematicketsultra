"""add checklist snapshot to pm bitacoras

Revision ID: d4f8b2c6e1a3
Revises: c3e7a1b5d9f2
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "d4f8b2c6e1a3"
down_revision = "c3e7a1b5d9f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pm_bitacoras",
        sa.Column("checklist_snapshot", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("pm_bitacoras", "checklist_snapshot")
