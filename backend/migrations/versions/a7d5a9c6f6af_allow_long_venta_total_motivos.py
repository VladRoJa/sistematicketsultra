"""Allow long venta total motivos

Revision ID: a7d5a9c6f6af
Revises: 8b5a75210d19
Create Date: 2026-05-07 14:47:35.568009

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a7d5a9c6f6af'
down_revision = '8b5a75210d19'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "venta_total_snapshot_rows",
        "motivo",
        existing_type=sa.VARCHAR(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "venta_total_snapshot_rows",
        "motivo",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )