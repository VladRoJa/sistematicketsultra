"""Add TotalPass Serrania alias

Revision ID: f4c2a8e71b36
Revises: d6b7e3f1a9c4
Create Date: 2026-09-16

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "f4c2a8e71b36"
down_revision = "d6b7e3f1a9c4"
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
            'totalpass_family',
            'ULTRAGYM Serranía',
            'SERRANIA',
            true,
            'Alias real observado en archivos TotalPass para Serranía.'
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
        WHERE source_family = 'totalpass_family'
          AND raw_branch_name = 'ULTRAGYM Serranía'
          AND sucursal_canon = 'SERRANIA';
        """
    )
