"""backfill track branch catalog sucursal ids

Revision ID: 422da9dde3bf
Revises: 6add09109634
Create Date: 2026-05-23 20:26:14.034934

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '422da9dde3bf'
down_revision = '6add09109634'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            UPDATE track_branch_catalog AS tbc
            SET sucursal_id = mapping.sucursal_id
            FROM (
                VALUES
                    ('VILLAS_DEL_REY', 1),
                    ('VILLA_VERDE', 2),
                    ('INDEPENDENCIA', 3),
                    ('TEC_MXL', 4),
                    ('SEND_MXL', 5),
                    ('SAN_LUIS', 6),
                    ('PABELLON_RTO', 7),
                    ('MISION_ENS', 8),
                    ('PASEO_2000', 9),
                    ('LOMA_BONITA', 10),
                    ('SANTA_FE', 11),
                    ('CARROUSEL_TJ', 12),
                    ('PAPALOTE_TJ', 13),
                    ('SEND_CUL', 14),
                    ('SAN_ISIDRO_CUL', 15),
                    ('AZAHARES_CUL', 16),
                    ('STA_CATARINA', 17),
                    ('SEND_SALTILLO', 18),
                    ('SEND_CHIH', 19),
                    ('PASEO_LA_PAZ', 20),
                    ('IXTAPALUCA', 21),
                    ('INSURGENTES', 22),
                    ('TLALNEPANTLA', 23),
                    ('METEPEC', 24),
                    ('SALTILLO_VILLALTA', 25)
            ) AS mapping(sucursal_canon, sucursal_id)
            WHERE tbc.sucursal_canon = mapping.sucursal_canon;
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            """
            UPDATE track_branch_catalog
            SET sucursal_id = NULL
            WHERE sucursal_canon IN (
                'VILLAS_DEL_REY',
                'VILLA_VERDE',
                'INDEPENDENCIA',
                'TEC_MXL',
                'SEND_MXL',
                'SAN_LUIS',
                'PABELLON_RTO',
                'MISION_ENS',
                'PASEO_2000',
                'LOMA_BONITA',
                'SANTA_FE',
                'CARROUSEL_TJ',
                'PAPALOTE_TJ',
                'SEND_CUL',
                'SAN_ISIDRO_CUL',
                'AZAHARES_CUL',
                'STA_CATARINA',
                'SEND_SALTILLO',
                'SEND_CHIH',
                'PASEO_LA_PAZ',
                'IXTAPALUCA',
                'INSURGENTES',
                'TLALNEPANTLA',
                'METEPEC',
                'SALTILLO_VILLALTA'
            );
            """
        )
    )
