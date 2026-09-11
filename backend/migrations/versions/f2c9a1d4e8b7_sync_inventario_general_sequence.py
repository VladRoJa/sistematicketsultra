"""Sync inventario_general id sequence with table max id.

Revision ID: f2c9a1d4e8b7
Revises: e7f6b4a91c2d
"""

from alembic import op


revision = "f2c9a1d4e8b7"
down_revision = "e7f6b4a91c2d"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence(
                'public.inventario_general',
                'id'
            )::regclass,
            COALESCE(MAX(id), 1),
            MAX(id) IS NOT NULL
        )
        FROM public.inventario_general
        """
    )


def downgrade():
    # Correccion operativa de secuencia: no se revierte a un valor inconsistente.
    pass
