"""seed track_branch_aliases manual_targets

Revision ID: f6298f01cfad
Revises: beb01990e3ec
Create Date: 2026-04-08 09:23:23.551735

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6298f01cfad'
down_revision = 'beb01990e3ec'
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
            ('manual_targets', 'VILLAS DEL REY', 'VILLAS_DEL_REY', true, NULL),
            ('manual_targets', 'VILLA VERDE', 'VILLA_VERDE', true, NULL),
            ('manual_targets', 'INDEPENDENCIA', 'INDEPENDENCIA', true, NULL),
            ('manual_targets', 'TEC MXL', 'TEC_MXL', true, NULL),
            ('manual_targets', 'SEND MXL', 'SEND_MXL', true, NULL),
            ('manual_targets', 'SAN LUIS', 'SAN_LUIS', true, NULL),
            ('manual_targets', 'PABELLON RTO', 'PABELLON_RTO', true, NULL),
            ('manual_targets', 'MISION ENS', 'MISION_ENS', true, NULL),
            ('manual_targets', 'PASEO 2000', 'PASEO_2000', true, NULL),
            ('manual_targets', 'LOMA BONITA', 'LOMA_BONITA', true, NULL),
            ('manual_targets', 'SANTA FE', 'SANTA_FE', true, NULL),
            ('manual_targets', 'CARROUSEL TJ', 'CARROUSEL_TJ', true, NULL),
            ('manual_targets', 'PAPALOTE TJ', 'PAPALOTE_TJ', true, NULL),
            ('manual_targets', 'SEND CUL', 'SEND_CUL', true, NULL),
            ('manual_targets', 'SAN ISIDRO CUL', 'SAN_ISIDRO_CUL', true, NULL),
            ('manual_targets', 'AZAHARES CUL', 'AZAHARES_CUL', true, NULL),
            ('manual_targets', 'STA CATARINA', 'STA_CATARINA', true, NULL),
            ('manual_targets', 'SEND SALTILLO', 'SEND_SALTILLO', true, NULL),
            ('manual_targets', 'SEND CHIH', 'SEND_CHIH', true, NULL),
            ('manual_targets', 'PASEO LA PAZ', 'PASEO_LA_PAZ', true, NULL),
            ('manual_targets', 'IXTAPALUCA', 'IXTAPALUCA', true, NULL),
            ('manual_targets', 'INSURGENTES', 'INSURGENTES', true, NULL),
            ('manual_targets', 'METEPEC', 'METEPEC', true, NULL),
            ('manual_targets', 'TLALNEPANTLA', 'TLALNEPANTLA', true, NULL),
            ('manual_targets', 'LA VIGA', 'LA_VIGA', true, NULL),
            ('manual_targets', 'SALTILLO VILLALTA', 'SALTILLO_VILLALTA', true, NULL);
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM track_branch_aliases
        WHERE source_family = 'manual_targets'
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