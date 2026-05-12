"""Add Serrania to Track catalog

Revision ID: 840a64d2ee63
Revises: 98faeb44881d
Create Date: 2026-05-12 12:58:13.364102

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '840a64d2ee63'
down_revision = '98faeb44881d'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO track_branch_catalog (
            sucursal_canon,
            track_label,
            display_order,
            is_track_active,
            notes
        )
        VALUES (
            'SERRANIA',
            'Serranía',
            (
                SELECT COALESCE(MAX(display_order), 0) + 10
                FROM track_branch_catalog
            ),
            true,
            'Alta formal por aparición de Serranía en fuentes Gasca.'
        )
        ON CONFLICT (sucursal_canon) DO UPDATE SET
            track_label = EXCLUDED.track_label,
            is_track_active = true,
            notes = EXCLUDED.notes;
        """
    )

    op.execute(
        """
        INSERT INTO track_branch_aliases (
            source_family,
            raw_branch_name,
            sucursal_canon,
            is_active,
            notes
        )
        VALUES
            (
                'gasca_family',
                'SERRANIA',
                'SERRANIA',
                true,
                'Alias formal para fuentes Gasca.'
            ),
            (
                'manual_targets',
                'SERRANIA',
                'SERRANIA',
                true,
                'Alias formal para metas manuales.'
            ),
            (
                'domiciliados_total',
                'SERRANIA',
                'SERRANIA',
                true,
                'Alias formal para fuente de domiciliados.'
            ),
            (
                'wellhub_family',
                'SERRANIA',
                'SERRANIA',
                true,
                'Alias preventivo para agregadora Wellhub.'
            ),
            (
                'totalpass_family',
                'SERRANIA',
                'SERRANIA',
                true,
                'Alias preventivo para agregadora TotalPass.'
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
        WHERE sucursal_canon = 'SERRANIA'
          AND raw_branch_name = 'SERRANIA'
          AND source_family IN (
              'gasca_family',
              'manual_targets',
              'domiciliados_total',
              'wellhub_family',
              'totalpass_family'
          );
        """
    )

    op.execute(
        """
        DELETE FROM track_branch_catalog
        WHERE sucursal_canon = 'SERRANIA';
        """
    )
