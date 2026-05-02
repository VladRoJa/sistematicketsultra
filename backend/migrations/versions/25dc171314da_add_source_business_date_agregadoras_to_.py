"""add source business date agregadoras to track daily mart

Revision ID: 25dc171314da
Revises: 5666dfd5931d
Create Date: 2026-04-30 12:43:23.206564

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '25dc171314da'
down_revision = '5666dfd5931d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "track_daily_mart",
        sa.Column("source_business_date_agregadoras", sa.Date(), nullable=True),
    )


def downgrade():
    op.drop_column(
        "track_daily_mart",
        "source_business_date_agregadoras",
    )