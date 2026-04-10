"""seed track_branch_aliases domiciliados_total

Revision ID: e4b41c73ff9d
Revises: de0a2e4275da
Create Date: 2026-04-10 08:33:49.152966

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4b41c73ff9d'
down_revision = 'de0a2e4275da'
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
        VALUES
            ('domiciliados_total', 'VILLAS DEL REY', 'VILLAS_DEL_REY', true, NULL),
            ('domiciliados_total', 'VILLA VERDE', 'VILLA_VERDE', true, NULL),
            ('domiciliados_total', 'INDEPENDENCIA', 'INDEPENDENCIA', true, NULL),
            ('domiciliados_total', 'TEC MXL', 'TEC_MXL', true, NULL),
            ('domiciliados_total', 'SEND MXL', 'SEND_MXL', true, NULL),
            ('domiciliados_total', 'SAN LUIS', 'SAN_LUIS', true, NULL),
            ('domiciliados_total', 'PABELLON RTO', 'PABELLON_RTO', true, NULL),
            ('domiciliados_total', 'MISION ENS', 'MISION_ENS', true, NULL),
            ('domiciliados_total', 'PASEO 2000', 'PASEO_2000', true, NULL),
            ('domiciliados_total', 'LOMA BONITA', 'LOMA_BONITA', true, NULL),
            ('domiciliados_total', 'SANTA FE', 'SANTA_FE', true, NULL),
            ('domiciliados_total', 'CARROUSEL TJ', 'CARROUSEL_TJ', true, NULL),
            ('domiciliados_total', 'PAPALOTE TJ', 'PAPALOTE_TJ', true, NULL),
            ('domiciliados_total', 'SEND CUL', 'SEND_CUL', true, NULL),
            ('domiciliados_total', 'SAN ISIDRO CUL', 'SAN_ISIDRO_CUL', true, NULL),
            ('domiciliados_total', 'AZAHARES CUL', 'AZAHARES_CUL', true, NULL),
            ('domiciliados_total', 'STA CATARINA', 'STA_CATARINA', true, NULL),
            ('domiciliados_total', 'SEND SALTILLO', 'SEND_SALTILLO', true, NULL),
            ('domiciliados_total', 'SEND CHIH', 'SEND_CHIH', true, NULL),
            ('domiciliados_total', 'PASEO LA PAZ', 'PASEO_LA_PAZ', true, NULL),
            ('domiciliados_total', 'IXTAPALUCA', 'IXTAPALUCA', true, NULL),
            ('domiciliados_total', 'INSURGENTES', 'INSURGENTES', true, NULL),
            ('domiciliados_total', 'METEPEC', 'METEPEC', true, NULL),
            ('domiciliados_total', 'TLALNEPANTLA', 'TLALNEPANTLA', true, NULL),
            ('domiciliados_total', 'LA VIGA', 'LA_VIGA', true, NULL),
            ('domiciliados_total', 'SALTILLO VILLALTA', 'SALTILLO_VILLALTA', true, NULL);
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM track_branch_aliases
        WHERE source_family = 'domiciliados_total'
          AND raw_branch_name IN (
            'VILLAS DEL REY',
            'VILLA VERDE',
            'INDEPENDENCIA',
            'TEC MXL',
            'SEND MXL',
            'SAN LUIS',
            'PABELLON RTO',
            'MISION ENS',
            'PASEO 2000',
            'LOMA BONITA',
            'SANTA FE',
            'CARROUSEL TJ',
            'PAPALOTE TJ',
            'SEND CUL',
            'SAN ISIDRO CUL',
            'AZAHARES CUL',
            'STA CATARINA',
            'SEND SALTILLO',
            'SEND CHIH',
            'PASEO LA PAZ',
            'IXTAPALUCA',
            'INSURGENTES',
            'METEPEC',
            'TLALNEPANTLA',
            'LA VIGA',
            'SALTILLO VILLALTA'
          );
        """
    )