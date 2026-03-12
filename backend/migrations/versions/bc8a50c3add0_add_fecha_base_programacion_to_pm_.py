"""add fecha_base_programacion to pm_preventivo_config

Revision ID: bc8a50c3add0
Revises: 4c70dac02bc7
Create Date: 2026-03-11 10:40:22.899656

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'bc8a50c3add0'
down_revision = '4c70dac02bc7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pm_preventivo_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fecha_base_programacion', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('pm_preventivo_config', schema=None) as batch_op:
        batch_op.drop_column('fecha_base_programacion')