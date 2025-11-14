"""Add costo_solucion y notas:cierre a ticket

Revision ID: 466c6cb7b37e
Revises: 8fda6e4996e8
Create Date: 2025-11-10 11:12:36.788346

"""
from alembic import op
import sqlalchemy as sa

revision = '466c6cb7b37e'
down_revision = '8fda6e4996e8'
branch_labels = None
depends_on = None


def upgrade():
    # Usamos SQL directo con IF NOT EXISTS para que no truene
    op.execute("""
        ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS costo_solucion NUMERIC(12, 2);
    """)

    op.execute("""
        ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS notas_cierre TEXT;
    """)


def downgrade():
    # Por si hay que revertir
    op.execute("""
        ALTER TABLE tickets
        DROP COLUMN IF EXISTS notas_cierre;
    """)

    op.execute("""
        ALTER TABLE tickets
        DROP COLUMN IF EXISTS costo_solucion;
    """)

    # ### end Alembic commands ###
