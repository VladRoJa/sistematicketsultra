"""add agregadoras consolidado generated report type

Revision ID: e2c4a6b8d0f1
Revises: d8e4f2a6c1b9
Create Date: 2026-09-29
"""

from alembic import op


revision = "e2c4a6b8d0f1"
down_revision = "d8e4f2a6c1b9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM warehouse_families
                WHERE key = 'reportes_transaccionales'
            ) THEN
                RAISE EXCEPTION
                    'No existe warehouse_families.key=reportes_transaccionales';
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM warehouse_operational_roles
                WHERE key = 'FUENTE_PRINCIPAL'
            ) THEN
                RAISE EXCEPTION
                    'No existe warehouse_operational_roles.key=FUENTE_PRINCIPAL';
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        INSERT INTO warehouse_sources (
            key,
            label,
            active
        )
        VALUES (
            'suite_auto',
            'Suite Ultra Automático',
            TRUE
        )
        ON CONFLICT (key)
        DO UPDATE SET
            label = EXCLUDED.label,
            active = TRUE;
        """
    )

    op.execute(
        """
        INSERT INTO warehouse_report_types (
            key,
            label,
            family_id,
            default_source_id,
            default_operational_role_id,
            default_period_type,
            active
        )
        SELECT
            'agregadoras_consolidado',
            'Consolidado de Agregadoras',
            family.id,
            source.id,
            role.id,
            'diario',
            TRUE
        FROM warehouse_families AS family
        JOIN warehouse_sources AS source
            ON source.key = 'suite_auto'
        JOIN warehouse_operational_roles AS role
            ON role.key = 'FUENTE_PRINCIPAL'
        WHERE family.key = 'reportes_transaccionales'
        ON CONFLICT (key)
        DO UPDATE SET
            label = EXCLUDED.label,
            family_id = EXCLUDED.family_id,
            default_source_id = EXCLUDED.default_source_id,
            default_operational_role_id =
                EXCLUDED.default_operational_role_id,
            default_period_type = EXCLUDED.default_period_type,
            active = TRUE;
        """
    )


def downgrade():
    op.execute(
        """
        DO $$
        DECLARE
            report_type_id_value INTEGER;
            source_id_value INTEGER;
        BEGIN
            SELECT id
            INTO report_type_id_value
            FROM warehouse_report_types
            WHERE key = 'agregadoras_consolidado'
            LIMIT 1;

            IF report_type_id_value IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1
                    FROM warehouse_uploads
                    WHERE report_type_id = report_type_id_value
                ) THEN
                    UPDATE warehouse_report_types
                    SET active = FALSE
                    WHERE id = report_type_id_value;
                ELSE
                    DELETE FROM warehouse_report_types
                    WHERE id = report_type_id_value;
                END IF;
            END IF;

            SELECT id
            INTO source_id_value
            FROM warehouse_sources
            WHERE key = 'suite_auto'
            LIMIT 1;

            IF source_id_value IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1
                   FROM warehouse_report_types
                   WHERE default_source_id = source_id_value
               )
               AND NOT EXISTS (
                   SELECT 1
                   FROM warehouse_uploads
                   WHERE source_id = source_id_value
               )
            THEN
                DELETE FROM warehouse_sources
                WHERE id = source_id_value;
            END IF;
        END
        $$;
        """
    )
