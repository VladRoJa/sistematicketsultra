"""replace track daily mart unique constraint with version branch index

Revision ID: 37ef17686d18
Revises: 359ea7512b12
Create Date: 2026-05-02 21:32:33.700724

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '37ef17686d18'
down_revision = '359ea7512b12'
branch_labels = None
depends_on = None

def upgrade():
    op.drop_index(
        "uq_track_daily_mart_date_mode_branch",
        table_name="track_daily_mart",
    )

    op.create_index(
        "uq_track_daily_mart_version_branch",
        "track_daily_mart",
        ["track_daily_version_id", "sucursal_canon"],
        unique=True,
        postgresql_where=sa.text("track_daily_version_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_track_daily_mart_version_branch",
        table_name="track_daily_mart",
    )

    op.create_index(
        "uq_track_daily_mart_date_mode_branch",
        "track_daily_mart",
        ["track_date", "generation_mode", "sucursal_canon"],
        unique=True,
    )