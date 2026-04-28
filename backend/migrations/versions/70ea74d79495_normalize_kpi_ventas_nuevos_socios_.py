"""normalize kpi ventas nuevos socios report type key

Revision ID: 70ea74d79495
Revises: ce2bc56fec0a
Create Date: 2026-04-28 07:53:18.175964

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '70ea74d79495'
down_revision = 'ce2bc56fec0a'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE warehouse_report_types
        SET key = 'kpi_ventas_nuevos_socios'
        WHERE key = 'kpi_ventas_nuevos'
          AND NOT EXISTS (
              SELECT 1
              FROM warehouse_report_types
              WHERE key = 'kpi_ventas_nuevos_socios'
          );
    """)


def downgrade():
    op.execute("""
        UPDATE warehouse_report_types
        SET key = 'kpi_ventas_nuevos'
        WHERE key = 'kpi_ventas_nuevos_socios'
          AND NOT EXISTS (
              SELECT 1
              FROM warehouse_report_types
              WHERE key = 'kpi_ventas_nuevos'
          );
    """)