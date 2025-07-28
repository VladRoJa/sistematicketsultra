"""Rename subsubcategoria to detalle in Ticket

Revision ID: e863de266d21
Revises: c5d477782860
Create Date: 2025-07-23 13:04:02.973066

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e863de266d21'
down_revision = 'c5d477782860'
branch_labels = None
depends_on = None


def upgrade():
    # Elimina la tabla migraciones_aplicadas si existe
    op.drop_table('migraciones_aplicadas')

    # ------- CATEGORÍAS -------
    with op.batch_alter_table('categorias', schema=None) as batch_op:
        # 1. Agrega la columna departamento_id como nullable
        batch_op.add_column(sa.Column('departamento_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('categorias_nombre_key', type_='unique')
        batch_op.create_foreign_key(None, 'departamentos', ['departamento_id'], ['id'])

    # 2. Llena valores nulos con un default (por ejemplo, 1 = departamento "General")
    op.execute('UPDATE categorias SET departamento_id = 1 WHERE departamento_id IS NULL')

    # 3. Ahora sí, hazla obligatoria
    with op.batch_alter_table('categorias', schema=None) as batch_op:
        batch_op.alter_column('departamento_id', nullable=False)

    # ------- TICKETS -------
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('detalle', sa.String(length=100), nullable=True))
        batch_op.alter_column('tipo_problema_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.drop_column('subsubcategoria')

    # 2. Llena tipo_problema_id nulos
    op.execute('UPDATE tickets SET tipo_problema_id = 1 WHERE tipo_problema_id IS NULL')

    # 3. Ahora sí, hazla NOT NULL
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.alter_column('tipo_problema_id', existing_type=sa.INTEGER(), nullable=False)


def downgrade():
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subsubcategoria', sa.String(length=100), nullable=True))
        batch_op.drop_column('detalle')
        batch_op.alter_column('tipo_problema_id', existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table('categorias', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_unique_constraint('categorias_nombre_key', ['nombre'])
        batch_op.drop_column('departamento_id')

    op.create_table('migraciones_aplicadas',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('nombre', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
        sa.Column('aplicada_en', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', name='migraciones_aplicadas_pkey'),
        sa.UniqueConstraint('nombre', name='migraciones_aplicadas_nombre_key')
    )

    # ### end Alembic commands ###
