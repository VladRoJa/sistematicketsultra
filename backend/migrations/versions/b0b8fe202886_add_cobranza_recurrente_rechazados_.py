"""add cobranza recurrente rechazados report type

Revision ID: b0b8fe202886
Revises: 027af445bc6b
Create Date: 2026-06-16 09:58:50.290334

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b0b8fe202886'
down_revision = '027af445bc6b'
branch_labels = None
depends_on = None


def upgrade():
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
            'cobranza_recurrente_rechazados',
            'Cobranza Recurrente Rechazados',
            f.id,
            s.id,
            r.id,
            'diario',
            true
        FROM warehouse_families f
        CROSS JOIN warehouse_sources s
        CROSS JOIN warehouse_operational_roles r
        WHERE f.key = 'reportes_transaccionales'
          AND s.key = 'gasca'
          AND r.key = 'FUENTE_PRINCIPAL'
          AND NOT EXISTS (
              SELECT 1
              FROM warehouse_report_types rt
              WHERE rt.key = 'cobranza_recurrente_rechazados'
          );
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM warehouse_report_types
        WHERE key = 'cobranza_recurrente_rechazados';
        """
    )