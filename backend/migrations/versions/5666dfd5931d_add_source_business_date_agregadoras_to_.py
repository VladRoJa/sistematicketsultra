"""add source business date agregadoras to track source ingresos daily

Revision ID: 5666dfd5931d
Revises: 9ba3a97b4ebe
Create Date: 2026-04-30 11:50:44.175870

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5666dfd5931d'
down_revision = '9ba3a97b4ebe'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "track_source_ingresos_daily",
        sa.Column("source_business_date_agregadoras", sa.Date(), nullable=True),
    )

def downgrade():
    op.drop_column(
        "track_source_ingresos_daily",
        "source_business_date_agregadoras",
    )