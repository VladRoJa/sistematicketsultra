"""seed track_branch_catalog initial

Revision ID: 25b6ff1b92d6
Revises: 214114c2361e
Create Date: 2026-04-08 09:13:01.989781

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '25b6ff1b92d6'
down_revision = '214114c2361e'
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
        VALUES
            ('VILLAS_DEL_REY', 'VILLAS DEL REY', 1, true, NULL),
            ('VILLA_VERDE', 'VILLA VERDE', 2, true, NULL),
            ('INDEPENDENCIA', 'INDEPENDENCIA', 3, true, NULL),
            ('TEC_MXL', 'TEC MXL', 4, true, NULL),
            ('SEND_MXL', 'SEND MXL', 5, true, NULL),
            ('SAN_LUIS', 'SAN LUIS', 6, true, NULL),
            ('PABELLON_RTO', 'PABELLON RTO', 7, true, NULL),
            ('MISION_ENS', 'MISION ENS', 8, true, NULL),
            ('PASEO_2000', 'PASEO 2000', 9, true, NULL),
            ('LOMA_BONITA', 'LOMA BONITA', 10, true, NULL),
            ('SANTA_FE', 'SANTA FE', 11, true, NULL),
            ('CARROUSEL_TJ', 'CARROUSEL TJ', 12, true, NULL),
            ('PAPALOTE_TJ', 'PAPALOTE TJ', 13, true, NULL),
            ('SEND_CUL', 'SEND CUL', 14, true, NULL),
            ('SAN_ISIDRO_CUL', 'SAN ISIDRO CUL', 15, true, NULL),
            ('AZAHARES_CUL', 'AZAHARES CUL', 16, true, NULL),
            ('STA_CATARINA', 'STA CATARINA', 17, true, NULL),
            ('SEND_SALTILLO', 'SEND SALTILLO', 18, true, NULL),
            ('SEND_CHIH', 'SEND CHIH', 19, true, NULL),
            ('PASEO_LA_PAZ', 'PASEO LA PAZ', 20, true, NULL),
            ('IXTAPALUCA', 'IXTAPALUCA', 21, true, NULL),
            ('INSURGENTES', 'INSURGENTES', 22, true, NULL),
            ('METEPEC', 'METEPEC', 23, true, NULL),
            ('TLALNEPANTLA', 'TLALNEPANTLA', 24, true, NULL),
            ('LA_VIGA', 'LA VIGA', 25, true, NULL),
            ('SALTILLO_VILLALTA', 'SALTILLO VILLALTA', 26, true, NULL);
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM track_branch_catalog
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
            'METEPEC',
            'TLALNEPANTLA',
            'LA_VIGA',
            'SALTILLO_VILLALTA'
        );
        """
    )