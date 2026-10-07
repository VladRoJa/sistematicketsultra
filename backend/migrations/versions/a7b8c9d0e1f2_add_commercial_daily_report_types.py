"""Catalog entries for automated commercial reports.

Revision ID: a7b8c9d0e1f2
Revises: d2f8a4c6b1e7, e1a7c4d2b9f6
"""
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = ("d2f8a4c6b1e7", "e1a7c4d2b9f6")
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO warehouse_report_types (
            key, label, family_id, default_source_id,
            default_operational_role_id, default_period_type, active
        )
        SELECT report.key, report.label, family.id, source.id,
               role.id, 'diario', TRUE
        FROM (VALUES
            ('comercial_venta_nueva_daily', 'Reporte diario Venta Nueva'),
            ('comercial_reactivaciones_daily', 'Reporte diario Reactivaciones')
        ) AS report(key, label)
        JOIN warehouse_families AS family ON family.key = 'reportes_transaccionales'
        JOIN warehouse_sources AS source ON source.key = 'suite_auto'
        JOIN warehouse_operational_roles AS role ON role.key = 'FUENTE_PRINCIPAL'
        ON CONFLICT (key) DO UPDATE SET
            label = EXCLUDED.label,
            family_id = EXCLUDED.family_id,
            default_source_id = EXCLUDED.default_source_id,
            default_operational_role_id = EXCLUDED.default_operational_role_id,
            default_period_type = EXCLUDED.default_period_type,
            active = TRUE;
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM warehouse_report_types
        WHERE key IN (
            'comercial_venta_nueva_daily',
            'comercial_reactivaciones_daily'
        )
        AND NOT EXISTS (
            SELECT 1 FROM warehouse_uploads AS upload
            WHERE upload.report_type_id = warehouse_report_types.id
        );
        """
    )
    op.execute(
        """
        UPDATE warehouse_report_types SET active = FALSE
        WHERE key IN (
            'comercial_venta_nueva_daily',
            'comercial_reactivaciones_daily'
        );
        """
    )
