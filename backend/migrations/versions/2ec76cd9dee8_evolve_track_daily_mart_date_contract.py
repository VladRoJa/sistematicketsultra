"""evolve track_daily_mart date contract

Revision ID: 2ec76cd9dee8
Revises: c3887fedf942
Create Date: 2026-04-10 12:34:43.645650

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2ec76cd9dee8'
down_revision = 'c3887fedf942'
branch_labels = None
depends_on = None



def upgrade():
    op.drop_index(
        "uq_track_daily_mart_date_branch",
        table_name="track_daily_mart",
    )

    op.alter_column(
        "track_daily_mart",
        "business_date",
        new_column_name="track_date",
        existing_type=sa.Date(),
        existing_nullable=False,
    )

    op.add_column(
        "track_daily_mart",
        sa.Column("source_business_date_desempeno", sa.Date(), nullable=True),
    )
    op.add_column(
        "track_daily_mart",
        sa.Column("source_business_date_ingresos", sa.Date(), nullable=True),
    )
    op.add_column(
        "track_daily_mart",
        sa.Column("source_business_date_nuevos", sa.Date(), nullable=True),
    )
    op.add_column(
        "track_daily_mart",
        sa.Column("source_business_date_domiciliados", sa.Date(), nullable=True),
    )

    op.create_index(
        "uq_track_daily_mart_track_date_branch",
        "track_daily_mart",
        ["track_date", "sucursal_canon"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_track_daily_mart_track_date_branch",
        table_name="track_daily_mart",
    )

    op.drop_column("track_daily_mart", "source_business_date_domiciliados")
    op.drop_column("track_daily_mart", "source_business_date_nuevos")
    op.drop_column("track_daily_mart", "source_business_date_ingresos")
    op.drop_column("track_daily_mart", "source_business_date_desempeno")

    op.alter_column(
        "track_daily_mart",
        "track_date",
        new_column_name="business_date",
        existing_type=sa.Date(),
        existing_nullable=False,
    )

    op.create_index(
        "uq_track_daily_mart_date_branch",
        "track_daily_mart",
        ["business_date", "sucursal_canon"],
        unique=True,
    )