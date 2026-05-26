"""backfill suite regional governance

Revision ID: 5ff71f6bff18
Revises: 4bc1e2356b56
Create Date: 2026-05-25 08:10:47.784311

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5ff71f6bff18'
down_revision = '4bc1e2356b56'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            INSERT INTO suite_regions (
                region_key,
                region_label,
                is_active,
                created_at,
                updated_at
            )
            VALUES
                ('MXL_SL', 'Mexicali / San Luis', true, now(), now()),
                ('TIJ_ROS_ENS', 'Tijuana / Rosarito / Ensenada', true, now(), now()),
                ('CLN_LP', 'Culiacán / La Paz', true, now(), now()),
                ('MTY_SALT_CHIH', 'Monterrey / Saltillo / Chihuahua', true, now(), now()),
                ('CDMX_IXT_TLAL', 'CDMX / Ixtapaluca / Tlalnepantla', true, now(), now()),
                ('NUEVAS', 'Nuevas / Por definir', true, now(), now())
            ON CONFLICT (region_key) DO UPDATE
            SET
                region_label = EXCLUDED.region_label,
                is_active = EXCLUDED.is_active,
                updated_at = now();
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO suite_sucursal_region_assignments (
                sucursal_id,
                region_id,
                is_current,
                valid_from,
                valid_to,
                created_at,
                updated_at
            )
            SELECT
                mapping.sucursal_id,
                sr.id AS region_id,
                true AS is_current,
                DATE '2026-05-25' AS valid_from,
                NULL::date AS valid_to,
                now() AS created_at,
                now() AS updated_at
            FROM (
                VALUES
                    (1, 'MXL_SL'),
                    (2, 'MXL_SL'),
                    (3, 'MXL_SL'),
                    (4, 'MXL_SL'),
                    (5, 'MXL_SL'),
                    (6, 'MXL_SL'),

                    (7, 'TIJ_ROS_ENS'),
                    (8, 'TIJ_ROS_ENS'),
                    (9, 'TIJ_ROS_ENS'),
                    (10, 'TIJ_ROS_ENS'),
                    (11, 'TIJ_ROS_ENS'),
                    (12, 'TIJ_ROS_ENS'),
                    (13, 'TIJ_ROS_ENS'),

                    (14, 'CLN_LP'),
                    (15, 'CLN_LP'),
                    (16, 'CLN_LP'),
                    (20, 'CLN_LP'),

                    (17, 'MTY_SALT_CHIH'),
                    (18, 'MTY_SALT_CHIH'),
                    (19, 'MTY_SALT_CHIH'),
                    (25, 'MTY_SALT_CHIH'),

                    (21, 'CDMX_IXT_TLAL'),
                    (22, 'CDMX_IXT_TLAL'),
                    (23, 'CDMX_IXT_TLAL'),
                    (24, 'CDMX_IXT_TLAL')

            ) AS mapping(sucursal_id, region_key)
            JOIN suite_regions sr
                ON sr.region_key = mapping.region_key
            ON CONFLICT (sucursal_id)
            WHERE is_current = true
            DO NOTHING;
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            """
            DELETE FROM suite_sucursal_region_assignments
            WHERE sucursal_id IN (
                1, 2, 3, 4, 5, 6,
                7, 8, 9, 10, 11, 12, 13,
                14, 15, 16, 20,
                17, 18, 19, 25,
                21, 22, 23, 24
            )
            AND is_current = true
            AND valid_from = DATE '2026-05-25';
            """
        )
    )

    op.execute(
        sa.text(
            """
            DELETE FROM suite_regions
            WHERE region_key IN (
                'MXL_SL',
                'TIJ_ROS_ENS',
                'CLN_LP',
                'MTY_SALT_CHIH',
                'CDMX_IXT_TLAL',
                'NUEVAS'
            );
            """
        )
    )