"""crear tabla usuario_sucursal

Revision ID: fcdf051532cf
Revises: 8fda6e4996e8
Create Date: 2026-02-27 09:46:25.111431

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fcdf051532cf'
down_revision = '4ff49cd61709'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'usuario_sucursal',
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sucursal_id', sa.Integer, sa.ForeignKey('sucursales.sucursal_id', ondelete='CASCADE'), nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'sucursal_id'),
    )

    op.execute("""
        INSERT INTO usuario_sucursal (user_id, sucursal_id)
        SELECT id, sucursal_id FROM users
        WHERE sucursal_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

def downgrade():
    op.drop_table('usuario_sucursal')