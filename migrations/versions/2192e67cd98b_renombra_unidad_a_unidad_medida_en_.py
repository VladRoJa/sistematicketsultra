"""Renombra unidad a unidad_medida en inventario_general

Revision ID: 2192e67cd98b
Revises: 0bb559c7ca7d
Create Date: 2025-07-14 06:18:44.455546

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2192e67cd98b'
down_revision = '0bb559c7ca7d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inventario_general', schema=None) as batch_op:
        # 1. Agrega la columna nueva
        batch_op.add_column(sa.Column('unidad_medida', sa.String(length=50), nullable=True))
    # 2. Copia los datos (usa SQL crudo porque Alembic no tiene ORM)
    op.execute('UPDATE inventario_general SET unidad_medida = unidad')
    with op.batch_alter_table('inventario_general', schema=None) as batch_op:
        # 3. Elimina la columna vieja
        batch_op.drop_column('unidad')


def downgrade():
    with op.batch_alter_table('inventario_general', schema=None) as batch_op:
        batch_op.add_column(sa.Column('unidad', sa.String(length=50), nullable=True))
    # Vuelve a copiar los datos (en reversa)
    op.execute('UPDATE inventario_general SET unidad = unidad_medida')
    with op.batch_alter_table('inventario_general', schema=None) as batch_op:
        batch_op.drop_column('unidad_medida')

    # ### end Alembic commands ###
