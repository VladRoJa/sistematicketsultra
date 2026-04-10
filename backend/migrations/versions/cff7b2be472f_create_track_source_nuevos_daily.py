"""create track_source_nuevos_daily

Revision ID: cff7b2be472f
Revises: de838fc72e6f
Create Date: 2026-04-09 17:59:59.513863

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cff7b2be472f'
down_revision = 'de838fc72e6f'
branch_labels = None
depends_on = None




def upgrade():
    op.create_table(
        "track_source_nuevos_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("clientes_nuevos_real_mtd", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("source_report_type_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            name="fk_track_source_nuevos_daily_sucursal_canon",
            ondelete="RESTRICT",
        ),
    )

    op.create_index(
        "uq_track_source_nuevos_daily_business_date_branch",
        "track_source_nuevos_daily",
        ["business_date", "sucursal_canon"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_track_source_nuevos_daily_business_date_branch",
        table_name="track_source_nuevos_daily",
    )
    op.drop_table("track_source_nuevos_daily")