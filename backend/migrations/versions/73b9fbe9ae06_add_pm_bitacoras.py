"""add pm_bitacoras

Revision ID: 73b9fbe9ae06
Revises: c86ee587c326
Create Date: 2026-03-02 08:01:44.186143

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '73b9fbe9ae06'
down_revision = 'c86ee587c326'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pm_bitacoras',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('inventario_id', sa.Integer(), nullable=False),
        sa.Column('sucursal_id', sa.Integer(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('resultado', sa.String(length=20), nullable=False),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('checks', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),

        sa.ForeignKeyConstraint(['inventario_id'], ['inventario_general.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    )

    op.create_index('ix_pm_bitacoras_inventario_id', 'pm_bitacoras', ['inventario_id'])
    op.create_index('ix_pm_bitacoras_sucursal_id', 'pm_bitacoras', ['sucursal_id'])
    op.create_index('ix_pm_bitacoras_fecha', 'pm_bitacoras', ['fecha'])
    op.create_index('ix_pm_bitacoras_created_by_user_id', 'pm_bitacoras', ['created_by_user_id'])

def downgrade():
    op.drop_index('ix_pm_bitacoras_created_by_user_id', table_name='pm_bitacoras')
    op.drop_index('ix_pm_bitacoras_fecha', table_name='pm_bitacoras')
    op.drop_index('ix_pm_bitacoras_sucursal_id', table_name='pm_bitacoras')
    op.drop_index('ix_pm_bitacoras_inventario_id', table_name='pm_bitacoras')
    op.drop_table('pm_bitacoras')