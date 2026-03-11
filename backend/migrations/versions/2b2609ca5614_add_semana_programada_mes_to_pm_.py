"""add semana_programada_mes to pm_preventivo_config

Revision ID: 2b2609ca5614
Revises: 2b89b372e06f
Create Date: 2026-03-10 11:20:03.696175

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2b2609ca5614'
down_revision = '2b89b372e06f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pm_preventivo_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('semana_programada_mes', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('pm_preventivo_config', schema=None) as batch_op:
        batch_op.drop_column('semana_programada_mes')