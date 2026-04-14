"""add generation_mode to track_daily_mart

Revision ID: 1478e746caf3
Revises: 2ec76cd9dee8
Create Date: 2026-04-14 09:37:31.098357

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1478e746caf3'
down_revision = '2ec76cd9dee8'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index(
        "uq_track_daily_mart_track_date_branch",
        table_name="track_daily_mart",
    )

    op.add_column(
        "track_daily_mart",
        sa.Column(
            "generation_mode",
            sa.Text(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE track_daily_mart
        SET generation_mode = 'official_closed_day'
        WHERE generation_mode IS NULL
        """
    )

    op.alter_column(
        "track_daily_mart",
        "generation_mode",
        existing_type=sa.Text(),
        nullable=False,
    )

    op.create_index(
        "uq_track_daily_mart_date_mode_branch",
        "track_daily_mart",
        ["track_date", "generation_mode", "sucursal_canon"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_track_daily_mart_date_mode_branch",
        table_name="track_daily_mart",
    )

    op.drop_column("track_daily_mart", "generation_mode")

    op.create_index(
        "uq_track_daily_mart_track_date_branch",
        "track_daily_mart",
        ["track_date", "sucursal_canon"],
        unique=True,
    )