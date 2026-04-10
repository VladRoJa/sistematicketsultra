"""seed track_branch_aliases gasca_family

Revision ID: beb01990e3ec
Revises: 25b6ff1b92d6
Create Date: 2026-04-08 09:17:27.689939

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'beb01990e3ec'
down_revision = '25b6ff1b92d6'
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
            ('gasca_family', 'VILLAS DEL REY', 'VILLAS_DEL_REY', true, NULL),
            ('gasca_family', 'VILLA VERDE', 'VILLA_VERDE', true, NULL),
            ('gasca_family', 'INDEPENDENCIA', 'INDEPENDENCIA', true, NULL),
            ('gasca_family', 'TEC MXL', 'TEC_MXL', true, NULL),
            ('gasca_family', 'SEND MXL', 'SEND_MXL', true, NULL),
            ('gasca_family', 'SAN LUIS', 'SAN_LUIS', true, NULL),
            ('gasca_family', 'PABELLON RTO', 'PABELLON_RTO', true, NULL),
            ('gasca_family', 'MISION ENS', 'MISION_ENS', true, NULL),
            ('gasca_family', 'PASEO 2000', 'PASEO_2000', true, NULL),
            ('gasca_family', 'LOMA BONITA', 'LOMA_BONITA', true, NULL),
            ('gasca_family', 'SANTA FE', 'SANTA_FE', true, NULL),
            ('gasca_family', 'CARROUSEL TJ', 'CARROUSEL_TJ', true, NULL),
            ('gasca_family', 'PAPALOTE TJ', 'PAPALOTE_TJ', true, NULL),
            ('gasca_family', 'SEND CUL', 'SEND_CUL', true, NULL),
            ('gasca_family', 'SAN ISIDRO CUL', 'SAN_ISIDRO_CUL', true, NULL),
            ('gasca_family', 'AZAHARES CUL', 'AZAHARES_CUL', true, NULL),
            ('gasca_family', 'STA CATARINA', 'STA_CATARINA', true, NULL),
            ('gasca_family', 'SEND SALTILLO', 'SEND_SALTILLO', true, NULL),
            ('gasca_family', 'SEND CHIH', 'SEND_CHIH', true, NULL),
            ('gasca_family', 'PASEO LA PAZ', 'PASEO_LA_PAZ', true, NULL),
            ('gasca_family', 'IXTAPALUCA', 'IXTAPALUCA', true, NULL),
            ('gasca_family', 'INSURGENTES', 'INSURGENTES', true, NULL),
            ('gasca_family', 'METEPEC', 'METEPEC', true, NULL),
            ('gasca_family', 'TLALNEPANTLA', 'TLALNEPANTLA', true, NULL),
            ('gasca_family', 'LA VIGA', 'LA_VIGA', true, NULL),
            ('gasca_family', 'SALTILLO VILLALTA', 'SALTILLO_VILLALTA', true, NULL);
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM track_branch_aliases
        WHERE source_family = 'gasca_family'
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