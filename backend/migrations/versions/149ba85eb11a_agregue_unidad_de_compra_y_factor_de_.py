"""agregue unidad de compra y factor de compra a inventariogeneral

Revision ID: 149ba85eb11a
Revises: 4f93c82e959c
Create Date: 2025-08-22 07:17:29.696215

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '149ba85eb11a'
down_revision = '4f93c82e959c'
branch_labels = None
depends_on = None


def upgrade():
    # ❌ Quitar esto si aparece por autogenerate:
    # op.drop_table('migraciones_aplicadas')

    with op.batch_alter_table('inventario_general', schema=None) as batch_op:
        batch_op.add_column(sa.Column('unidad_compra', sa.String(length=50), nullable=True))
        # Agregar NOT NULL con default para no romper filas existentes
        batch_op.add_column(sa.Column('factor_compra', sa.Integer(), nullable=False, server_default='1'))

    # Quitar el default del esquema (opcional)
    with op.batch_alter_table('inventario_general', schema=None) as batch_op:
        batch_op.alter_column('factor_compra', server_default=None)

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('inventario_general', schema=None) as batch_op:
        batch_op.drop_column('factor_compra')
        batch_op.drop_column('unidad_compra')
