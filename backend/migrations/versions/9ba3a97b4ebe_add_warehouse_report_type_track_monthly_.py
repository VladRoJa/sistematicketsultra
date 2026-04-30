"""add warehouse report type track monthly targets

Revision ID: 9ba3a97b4ebe
Revises: 70ea74d79495
Create Date: 2026-04-28 10:43:56.957071

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9ba3a97b4ebe'
down_revision = '70ea74d79495'
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
            'track_monthly_targets',
            'Track Monthly Targets',
            wf.id,
            ws.id,
            wor.id,
            'mensual',
            true
        FROM warehouse_families wf
        CROSS JOIN warehouse_sources ws
        CROSS JOIN warehouse_operational_roles wor
        WHERE wf.key = 'reportes_transaccionales'
          AND ws.key = 'manual'
          AND wor.key = 'FUENTE_AUXILIAR_ENRIQUECIMIENTO'
          AND NOT EXISTS (
              SELECT 1
              FROM warehouse_report_types wrt
              WHERE wrt.key = 'track_monthly_targets'
          );
        """
    )
    
def downgrade():
    op.execute(
        """
        DELETE FROM warehouse_report_types
        WHERE key = 'track_monthly_targets';
        """
    )