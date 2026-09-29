"""add agregadoras consolidado template report type

Revision ID: d8e4f2a6c1b9
Revises: c7d2e5f8a1b4
Create Date: 2026-09-29
"""

from alembic import op


revision = "d8e4f2a6c1b9"
down_revision = "c7d2e5f8a1b4"
branch_labels = None
depends_on = None


REPORT_TYPE_KEY = "agregadoras_consolidado_template"


def upgrade():
    op.execute(
        """
        DO $$
        DECLARE
            family_id_value INTEGER;
            source_id_value INTEGER;
            role_id_value INTEGER;
        BEGIN
            SELECT id
            INTO family_id_value
            FROM warehouse_families
            WHERE key = 'catalogos_auxiliares'
            LIMIT 1;

            IF family_id_value IS NULL THEN
                RAISE EXCEPTION
                    'No existe warehouse_families.key=catalogos_auxiliares';
            END IF;

            SELECT id
            INTO source_id_value
            FROM warehouse_sources
            WHERE key = 'manual'
            LIMIT 1;

            IF source_id_value IS NULL THEN
                RAISE EXCEPTION
                    'No existe warehouse_sources.key=manual';
            END IF;

            SELECT id
            INTO role_id_value
            FROM warehouse_operational_roles
            WHERE key = 'CATALOGO_AUXILIAR'
            LIMIT 1;

            IF role_id_value IS NULL THEN
                RAISE EXCEPTION
                    'No existe warehouse_operational_roles.key=CATALOGO_AUXILIAR';
            END IF;

            INSERT INTO warehouse_report_types (
                key,
                label,
                family_id,
                default_source_id,
                default_operational_role_id,
                default_period_type,
                active
            )
            VALUES (
                'agregadoras_consolidado_template',
                'Plantilla Consolidado Agregadoras',
                family_id_value,
                source_id_value,
                role_id_value,
                'diario',
                TRUE
            )
            ON CONFLICT (key)
            DO UPDATE SET
                label = EXCLUDED.label,
                family_id = EXCLUDED.family_id,
                default_source_id = EXCLUDED.default_source_id,
                default_operational_role_id = EXCLUDED.default_operational_role_id,
                default_period_type = EXCLUDED.default_period_type,
                active = TRUE;
        END
        $$;
        """
    )


def downgrade():
    op.execute(
        """
        DO $$
        DECLARE
            report_type_id_value INTEGER;
        BEGIN
            SELECT id
            INTO report_type_id_value
            FROM warehouse_report_types
            WHERE key = 'agregadoras_consolidado_template'
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
        END
        $$;
        """
    )
