"""Register the generated iVentas activity reports in Warehouse."""

from alembic import op


revision = "i19c11202601"
down_revision = "m1233bimulti111026"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO warehouse_report_types (
            key, label, family_id, default_source_id,
            default_operational_role_id, default_period_type, active
        )
        SELECT report.key, report.label, family.id, source.id, role.id, 'rango', TRUE
        FROM (VALUES
            ('iventas_actividad_horaria', 'iVentas - Delta horario'),
            ('iventas_actividad_acumulado_horario', 'iVentas - Acumulado por hora')
        ) AS report(key, label)
        JOIN warehouse_families AS family ON family.key = 'reportes_transaccionales'
        JOIN warehouse_sources AS source ON source.key = 'suite_auto'
        JOIN warehouse_operational_roles AS role ON role.key = 'FUENTE_PRINCIPAL'
        ON CONFLICT (key) DO UPDATE SET label = EXCLUDED.label, active = TRUE;
    """)


def downgrade():
    op.execute("""
        DELETE FROM warehouse_report_types
        WHERE key IN ('iventas_actividad_horaria', 'iventas_actividad_acumulado_horario')
        AND NOT EXISTS (
            SELECT 1 FROM warehouse_uploads AS upload
            WHERE upload.report_type_id = warehouse_report_types.id
        );
    """)
    op.execute("""
        UPDATE warehouse_report_types SET active = FALSE
        WHERE key IN ('iventas_actividad_horaria', 'iventas_actividad_acumulado_horario');
    """)
