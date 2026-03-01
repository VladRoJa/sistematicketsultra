"""add por_validar to estado_ticket_enum

Revision ID: c86ee587c326
Revises: fcdf051532cf
Create Date: 2026-03-01 14:50:11.165374

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c86ee587c326'
down_revision = 'fcdf051532cf'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("COMMIT")
    op.execute("ALTER TYPE estado_ticket_enum ADD VALUE IF NOT EXISTS 'por_validar'")

def downgrade():
    pass
