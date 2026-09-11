"""Sync inventario_sucursal id sequence with table max id.

Revision ID: e7f6b4a91c2d
Revises: d5a2c7e9f104
"""

from alembic import op


revision = "e7f6b4a91c2d"
down_revision = "d5a2c7e9f104"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence(
                'public.inventario_sucursal',
                'id'
            )::regclass,
            COALESCE(MAX(id), 1),
            MAX(id) IS NOT NULL
        )
        FROM public.inventario_sucursal
        """
    )


def downgrade():
    # Correccion operativa de secuencia: no se revierte a un valor inconsistente.
    pass
