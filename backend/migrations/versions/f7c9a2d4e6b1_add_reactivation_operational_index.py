"""add reactivation operational latest index

Revision ID: f7c9a2d4e6b1
Revises: e6b8c4d2f1a0
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "f7c9a2d4e6b1"
down_revision = "e6b8c4d2f1a0"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_socios_vencidos_cartera_operational_latest"


def upgrade():
    op.create_index(
        INDEX_NAME,
        "socios_vencidos_cartera",
        [
            "sucursal_key",
            "pin",
            sa.text("fecha_vencimiento_date DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )


def downgrade():
    op.drop_index(
        INDEX_NAME,
        table_name="socios_vencidos_cartera",
    )
