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


# Reference snapshot supplied from production on 2026-11-07 (public branch data).
# This revision PRECEDES the c9/a7 identity-normalization migrations:
# at this point 24 is METEPEC and 25 is SALTILLO VILLALTA. The later
# migrations swap them into their official final IDs 25 and 24.
# Never seed final IDs 24/25 here: that would reassign business identity.
_CLEAN_BOOTSTRAP_SUCURSALES_PRE_C9 = (
    (1, "VREY", "Villas del rey", "Baja California", "Mexicali", "CALZADA XOCHIMILCO #200"),
    (2, "VVER", "Villa verde mexicali", "Baja California", "Mexicali", "BLV. LAZARO CARDENAS COL. DIEZ DIVISION DOS"),
    (3, "INDE", "Independencia", "Baja California", "Mexicali", "CALZADA INDEPENDENCIA S/N"),
    (4, "TECN", "Tec mexicali", "Baja California", "Mexicali", "BLVD LAZARO CARDENAS #2338 LOTE 7"),
    (5, "SMXL", "Sendero mexicali", "Baja California", "Mexicali", "1600 AV, BLVRD LAZARO CARDENAS"),
    (6, "SLUI", "San luis", "Sonora", "San Luis Rio Colorado", "CALLEJON GUADALUPE VICTORIA #1709"),
    (7, "PABE", "Pabellon rosarito", "Baja California", "Playas de Rosarito", "CARRETERA A TIJUANA ENSENADA NO 300"),
    (8, "MISI", "Mision ensenada", "Baja California", "Ensenada", "REFORMA Y C ONCE NO 1122"),
    (9, "PASS", "Paseo 2000", "Baja California", "Tijuana", "CORREDOR TIJUANA ROSARITO 2000 26135 LOCAL PAD-D"),
    (10, "LBON", "Loma bonita", "Baja California", "Tijuana", "BLVD AGUA AZUL NUM 7200"),
    (11, "SAFE", "Santa fe", "Baja California", "Tijuana", "BLVD EL ROSARIO NUM 10450"),
    (12, "CARR", "Carrousel tijuana", "Baja California", "Tijuana", "CIPRES 4, LAS BRISAS, 22115 TIJUANA, B.C."),
    (13, "PAPA", "Papalote tijuana", "Baja California", "Tijuana", "INSURGENTES NO 16902"),
    (14, "SCLN", "Sendero culiacan", "Sinaloa", "Culiacan", "CUG SENDERO CULIACAN"),
    (15, "SISI", "San isidro culiacan", "Sinaloa", "Culiacan", "CUG SAN ISIDRO"),
    (16, "AZAH", "Azahares culiacan", "Sinaloa", "Culiacan", "CUG AZAHARES CULIACAN"),
    (17, "SCAT", "Santa catarina", "Nuevo Leon", "Santa Catarina", "CARR MONTERREY SALTILLO 2601"),
    (18, "SSAL", "Sendero saltillo", "Coahuila de Zaragoza", "Saltillo", "BLVD. ANTONIO CARDENAS 4159, PARQUES DE LA CANADA, 25080 SALTILLO, COAH."),
    (19, "SCHI", "Sendero chihuahua", "Chihuahua", "Chihuahua", "ALEJANDRO DUMAS #11337"),
    (20, "LPAZ", "Paseo la paz", "Baja California Sur", "La Paz", "LIB DANIEL ROLDAN"),
    (21, "IXTA", "Ixtapaluca", "Mexico", "Ixtapaluca", "CARR FEDERAL MEXICO-CUAUTLA 1"),
    (22, "INSU", "Insurgentes", "Mexico", "Tlalpan", "Insurgentes sur 3838"),
    (23, "TLAL", "Tlalnepantla", "Mexico", "s/m", "-"),
    (24, "METE", "Metepec", "Mexico", "Toluca", "-"),
    (25, "SVIL", "Saltillo Villalta", "Monterrey", "Saltillo", "-"),
    (26, "SERR", "Serranía", "Nuevo Leon", "Monterrey", "Plaza Serrania / Cumbres Monterrey"),
)


def _seed_sucursales_if_pristine(connection):
    # The original installation relied on operational reference data loaded
    # outside Alembic. A brand-new database has an empty parent table; only
    # that exact state qualifies for the deterministic initial seed.
    count = connection.execute(
        sa.text("SELECT COUNT(*) FROM sucursales")
    ).scalar_one()
    if count:
        # Never reconcile, overwrite, or append to an existing master catalog.
        return

    connection.execute(
        sa.text(
            """
            INSERT INTO sucursales (
                sucursal_id, serie, sucursal, estado, municipio, direccion
            ) VALUES (
                :sucursal_id, :serie, :sucursal, :estado,
                :municipio, :direccion
            )
            """
        ),
        [
            {
                "sucursal_id": branch_id,
                "serie": serie,
                "sucursal": sucursal,
                "estado": estado,
                "municipio": municipio,
                "direccion": direccion,
            }
            for branch_id, serie, sucursal, estado, municipio, direccion
            in _CLEAN_BOOTSTRAP_SUCURSALES_PRE_C9
        ],
    )


def upgrade():
    _seed_sucursales_if_pristine(op.get_bind())
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
    # Never delete branch master records: later modules may reference them.
    # The original downgrade only removes the Track FK backfill.
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
