"""create track_source_domiciliados_daily

Revision ID: bee381d1c22f
Revises: e4b41c73ff9d
Create Date: 2026-04-10 08:40:03.520433

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bee381d1c22f'
down_revision = 'e4b41c73ff9d'
branch_labels = None
depends_on = None



def upgrade():
    op.create_table(
        "track_source_domiciliados_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("nuevos_domiciliados_real_mtd", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("source_report_type_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            name="fk_track_source_domiciliados_daily_sucursal_canon",
            ondelete="RESTRICT",
        ),
    )

    op.create_index(
        "uq_track_source_domiciliados_daily_business_date_branch",
        "track_source_domiciliados_daily",
        ["business_date", "sucursal_canon"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_track_source_domiciliados_daily_business_date_branch",
        table_name="track_source_domiciliados_daily",
    )
    op.drop_table("track_source_domiciliados_daily")