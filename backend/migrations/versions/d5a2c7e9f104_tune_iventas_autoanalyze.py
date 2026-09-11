"""Tune iVentas Marketing autoanalyze thresholds.

Revision ID: d5a2c7e9f104
Revises: c4f1a8e7b6d2
"""

from alembic import op


revision = "d5a2c7e9f104"
down_revision = "c4f1a8e7b6d2"
branch_labels = None
depends_on = None


TABLES = (
    "marketing_iventas_contacts",
    "marketing_iventas_contact_tags",
)


def upgrade():
    for table_name in TABLES:
        op.execute(
            f"""
            ALTER TABLE {table_name}
            SET (
                autovacuum_analyze_scale_factor = 0.01,
                autovacuum_analyze_threshold = 1000
            )
            """
        )


def downgrade():
    for table_name in TABLES:
        op.execute(
            f"""
            ALTER TABLE {table_name}
            RESET (
                autovacuum_analyze_scale_factor,
                autovacuum_analyze_threshold
            )
            """
        )
