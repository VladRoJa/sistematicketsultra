"""add dia_programado_semana to pm_preventivo_config

Revision ID: 4c70dac02bc7
Revises: 2b2609ca5614
Create Date: 2026-03-11 08:01:59.496211

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4c70dac02bc7'
down_revision = '2b2609ca5614'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pm_preventivo_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dia_programado_semana', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('pm_preventivo_config', schema=None) as batch_op:
        batch_op.drop_column('dia_programado_semana')