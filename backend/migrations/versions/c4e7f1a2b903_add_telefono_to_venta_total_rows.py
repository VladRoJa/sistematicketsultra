"""add telefono to venta total snapshot rows

Revision ID: c4e7f1a2b903
Revises: 15b6c8f131ad
Create Date: 2026-07-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c4e7f1a2b903"
down_revision = "15b6c8f131ad"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "venta_total_snapshot_rows",
        sa.Column(
            "telefono",
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_venta_total_snapshot_rows_telefono",
        "venta_total_snapshot_rows",
        ["telefono"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_venta_total_snapshot_rows_telefono",
        table_name="venta_total_snapshot_rows",
    )
    op.drop_column(
        "venta_total_snapshot_rows",
        "telefono",
    )
