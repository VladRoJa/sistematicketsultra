"""add api to venta total rows

Revision ID: c4e7a9b2d6f1
Revises: a2d5f8c1b3e7
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa


revision = "c4e7a9b2d6f1"
down_revision = "a2d5f8c1b3e7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "venta_total_snapshot_rows",
        sa.Column("api", sa.String(length=100), nullable=True),
    )


def downgrade():
    op.drop_column("venta_total_snapshot_rows", "api")
