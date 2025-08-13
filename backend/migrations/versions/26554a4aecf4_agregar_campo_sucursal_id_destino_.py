"""Agregar campo sucursal_id_destino obligatorio a tickets

Revision ID: 26554a4aecf4
Revises: 708ba4302146
Create Date: 2025-08-08 12:26:58.418020
"""
from alembic import op
import sqlalchemy as sa

revision = '26554a4aecf4'
down_revision = '708ba4302146'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tickets', sa.Column('sucursal_id_destino', sa.Integer(), nullable=True))

    op.execute("""
        UPDATE tickets
        SET sucursal_id_destino = COALESCE(sucursal_id_destino, sucursal_id)
    """)

    op.alter_column('tickets', 'sucursal_id_destino', nullable=False)

    op.create_foreign_key(
        'fk_tickets_sucursal_destino',
        'tickets', 'sucursales',
        ['sucursal_id_destino'], ['sucursal_id'],
        ondelete='RESTRICT'
    )

def downgrade():
    op.drop_constraint('fk_tickets_sucursal_destino', 'tickets', type_='foreignkey')
    op.drop_column('tickets', 'sucursal_id_destino')
