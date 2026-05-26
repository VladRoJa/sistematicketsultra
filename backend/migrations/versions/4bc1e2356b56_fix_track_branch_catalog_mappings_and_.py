"""fix track branch catalog mappings and order

Revision ID: 4bc1e2356b56
Revises: 0e96bf84836b
Create Date: 2026-05-25 08:06:40.925856

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bc1e2356b56'
down_revision = '0e96bf84836b'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            UPDATE track_branch_catalog
            SET display_order = CASE sucursal_canon
                WHEN 'METEPEC' THEN -101
                WHEN 'TLALNEPANTLA' THEN -102
                WHEN 'SALTILLO_VILLALTA' THEN -103
                WHEN 'LA_VIGA' THEN -104
                WHEN 'SERRANIA' THEN -105
                ELSE display_order
            END
            WHERE sucursal_canon IN (
                'METEPEC',
                'TLALNEPANTLA',
                'SALTILLO_VILLALTA',
                'LA_VIGA',
                'SERRANIA'
            );

            UPDATE track_branch_catalog AS tbc
            SET
                sucursal_id = mapping.sucursal_id,
                display_order = mapping.display_order
            FROM (
                VALUES
                    ('TLALNEPANTLA', 24, 23),
                    ('SALTILLO_VILLALTA', 25, 24),
                    ('METEPEC', 23, 25),
                    ('LA_VIGA', NULL::integer, 26),
                    ('SERRANIA', NULL::integer, 27)
            ) AS mapping(sucursal_canon, sucursal_id, display_order)
            WHERE tbc.sucursal_canon = mapping.sucursal_canon;
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            """
            UPDATE track_branch_catalog
            SET display_order = CASE sucursal_canon
                WHEN 'METEPEC' THEN -101
                WHEN 'TLALNEPANTLA' THEN -102
                WHEN 'SALTILLO_VILLALTA' THEN -103
                WHEN 'LA_VIGA' THEN -104
                WHEN 'SERRANIA' THEN -105
                ELSE display_order
            END
            WHERE sucursal_canon IN (
                'METEPEC',
                'TLALNEPANTLA',
                'SALTILLO_VILLALTA',
                'LA_VIGA',
                'SERRANIA'
            );

            UPDATE track_branch_catalog AS tbc
            SET
                sucursal_id = mapping.sucursal_id,
                display_order = mapping.display_order
            FROM (
                VALUES
                    ('METEPEC', 24, 23),
                    ('TLALNEPANTLA', 23, 24),
                    ('LA_VIGA', NULL::integer, 25),
                    ('SALTILLO_VILLALTA', 25, 26),
                    ('SERRANIA', NULL::integer, 27)
            ) AS mapping(sucursal_canon, sucursal_id, display_order)
            WHERE tbc.sucursal_canon = mapping.sucursal_canon;
            """
        )
    )