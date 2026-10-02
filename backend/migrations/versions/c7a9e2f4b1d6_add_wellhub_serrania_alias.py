"""add Wellhub Serrania alias

Revision ID: c7a9e2f4b1d6
Revises: f2c7a1d9e4b6
Create Date: 2026-10-02
"""

from alembic import op


revision = "c7a9e2f4b1d6"
down_revision = "f2c7a1d9e4b6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO track_branch_aliases (
            source_family,
            raw_branch_name,
            sucursal_canon,
            is_active,
            notes
        )
        VALUES (
            'wellhub_family',
            'Ultra -   Serranía',
            'SERRANIA',
            true,
            'Alias oficial de Serranía recibido desde Wellhub.'
        )
        ON CONFLICT (source_family, raw_branch_name) DO UPDATE SET
            sucursal_canon = EXCLUDED.sucursal_canon,
            is_active = true,
            notes = EXCLUDED.notes;
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM track_branch_aliases
        WHERE source_family = 'wellhub_family'
          AND raw_branch_name = 'Ultra -   Serranía'
          AND sucursal_canon = 'SERRANIA';
        """
    )
