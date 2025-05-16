"""Agregar columna url_evidencia a tickets

Revision ID: 80adae9b5acc
Revises: 
Create Date: 2025-05-13 11:29:47.073275

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '80adae9b5acc'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('url_evidencia', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_column('url_evidencia')
