"""add tipo_mantenimiento to pm_bitacoras

Revision ID: 2b89b372e06f
Revises: e9304aa26307
Create Date: 2026-03-09 14:21:34.826215

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2b89b372e06f'
down_revision = 'e9304aa26307'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pm_bitacoras', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tipo_mantenimiento', sa.String(length=20), nullable=True))

def downgrade():
    with op.batch_alter_table('pm_bitacoras', schema=None) as batch_op:
        batch_op.drop_column('tipo_mantenimiento')