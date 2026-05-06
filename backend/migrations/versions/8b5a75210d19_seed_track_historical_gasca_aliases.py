"""seed track historical gasca aliases

Revision ID: 8b5a75210d19
Revises: f3e664c0e45a
Create Date: 2026-05-06 14:20:47.839241

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b5a75210d19'
down_revision = 'f3e664c0e45a'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            INSERT INTO track_branch_aliases (
                source_family,
                raw_branch_name,
                sucursal_canon,
                is_active,
                notes
            )
            SELECT
                v.source_family,
                v.raw_branch_name,
                v.sucursal_canon,
                true,
                'Alias histórico para backfill Track 2025; nombres largos usados en reportes legacy.'
            FROM (
                VALUES
                    ('gasca_family', 'AZAHARES CULIACAN', 'AZAHARES_CUL'),
                    ('gasca_family', 'CARROUSEL TIJUANA', 'CARROUSEL_TJ'),
                    ('gasca_family', 'MISION ENSENADA', 'MISION_ENS'),
                    ('gasca_family', 'PABELLON ROSARITO', 'PABELLON_RTO'),
                    ('gasca_family', 'PAPALOTE TIJUANA', 'PAPALOTE_TJ'),
                    ('gasca_family', 'SAN ISIDRO CULIACAN', 'SAN_ISIDRO_CUL'),
                    ('gasca_family', 'SANTA CATARINA', 'STA_CATARINA'),
                    ('gasca_family', 'SENDERO CHIHUAHUA', 'SEND_CHIH'),
                    ('gasca_family', 'SENDERO CULIACAN', 'SEND_CUL'),
                    ('gasca_family', 'SENDERO MEXICALI', 'SEND_MXL'),
                    ('gasca_family', 'SENDERO SALTILLO', 'SEND_SALTILLO'),
                    ('gasca_family', 'TEC MEXICALI', 'TEC_MXL'),
                    ('gasca_family', 'VILLA VERDE MEXICALI', 'VILLA_VERDE')
            ) AS v(source_family, raw_branch_name, sucursal_canon)
            WHERE NOT EXISTS (
                SELECT 1
                FROM track_branch_aliases a
                WHERE a.source_family = v.source_family
                  AND LOWER(TRIM(a.raw_branch_name)) = LOWER(TRIM(v.raw_branch_name))
            );
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            """
            DELETE FROM track_branch_aliases
            WHERE source_family = 'gasca_family'
              AND raw_branch_name IN (
                  'AZAHARES CULIACAN',
                  'CARROUSEL TIJUANA',
                  'MISION ENSENADA',
                  'PABELLON ROSARITO',
                  'PAPALOTE TIJUANA',
                  'SAN ISIDRO CULIACAN',
                  'SANTA CATARINA',
                  'SENDERO CHIHUAHUA',
                  'SENDERO CULIACAN',
                  'SENDERO MEXICALI',
                  'SENDERO SALTILLO',
                  'TEC MEXICALI',
                  'VILLA VERDE MEXICALI'
              )
              AND notes = 'Alias histórico para backfill Track 2025; nombres largos usados en reportes legacy.';
            """
        )
    )