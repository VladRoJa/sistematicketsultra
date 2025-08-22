"""catalogo categorias inventario

Revision ID: 995b3ba7aacd
Revises: 149ba85eb11a
Create Date: 2025-08-22 10:06:28.975975

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '995b3ba7aacd'
down_revision = '149ba85eb11a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'catalogo_categoria_inventario',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombre', sa.String(length=120), nullable=False, unique=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('creado_en', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('actualizado_en', sa.DateTime(), nullable=True),
    )

def downgrade():
    op.drop_table('catalogo_categoria_inventario')
