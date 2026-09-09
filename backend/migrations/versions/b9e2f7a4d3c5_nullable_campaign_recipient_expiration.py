"""Allow campaign recipients without an expired membership.

Revision ID: b9e2f7a4d3c5
Revises: a8d1e6f3c2b4
"""

from alembic import op
import sqlalchemy as sa


revision = "b9e2f7a4d3c5"
down_revision = "a8d1e6f3c2b4"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "marketing_reactivation_campaign_recipients",
        "socios_vencidos_cartera_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        "marketing_reactivation_campaign_recipients",
        "fecha_vencimiento_date",
        existing_type=sa.Date(),
        nullable=True,
    )


def downgrade():
    # PostgreSQL rejects this downgrade if NULLs exist; preserve those records.
    op.alter_column(
        "marketing_reactivation_campaign_recipients",
        "fecha_vencimiento_date",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.alter_column(
        "marketing_reactivation_campaign_recipients",
        "socios_vencidos_cartera_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
