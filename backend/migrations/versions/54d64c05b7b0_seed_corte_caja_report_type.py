"""Seed corte caja report type

Revision ID: 54d64c05b7b0
Revises: a7d5a9c6f6af
Create Date: 2026-05-08 10:43:23.256298

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '54d64c05b7b0'
down_revision = 'a7d5a9c6f6af'
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
            'corte_caja',
            'Corte de Caja',
            2,
            1,
            1,
            'rango',
            true
        WHERE NOT EXISTS (
            SELECT 1
            FROM warehouse_report_types
            WHERE key = 'corte_caja'
        );
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE warehouse_report_types
        SET active = false
        WHERE key = 'corte_caja';
        """
    )