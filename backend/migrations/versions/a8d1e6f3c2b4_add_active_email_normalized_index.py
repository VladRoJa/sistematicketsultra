"""add active member normalized email index

Revision ID: a8d1e6f3c2b4
Revises: f7c9a2d4e6b1
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "a8d1e6f3c2b4"
down_revision = "f7c9a2d4e6b1"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_socios_activos_rows_snapshot_email_normalized"


def upgrade():
    op.create_index(
        INDEX_NAME,
        "socios_activos_snapshot_rows",
        [
            "snapshot_id",
            sa.text("lower(btrim(email_raw))"),
        ],
        unique=False,
    )


def downgrade():
    op.drop_index(
        INDEX_NAME,
        table_name="socios_activos_snapshot_rows",
    )
