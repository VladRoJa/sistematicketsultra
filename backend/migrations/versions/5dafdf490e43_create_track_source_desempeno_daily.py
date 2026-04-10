"""create track_source_desempeno_daily

Revision ID: 5dafdf490e43
Revises: 1478ce6503b9
Create Date: 2026-04-08 12:35:32.139642

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5dafdf490e43'
down_revision = '1478ce6503b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "track_source_desempeno_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("usuarios_activos_actual", sa.Integer(), nullable=False),
        sa.Column("reactivaciones_real_mtd", sa.Integer(), nullable=False),
        sa.Column("bajas_reales_mtd", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("source_report_type_key", sa.Text(), nullable=False),

        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            name="fk_track_source_desempeno_daily_sucursal_canon",
            ondelete="RESTRICT",
        ),
    )

    op.create_index(
        "uq_track_source_desempeno_daily_business_date_branch",
        "track_source_desempeno_daily",
        ["business_date", "sucursal_canon"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_track_source_desempeno_daily_business_date_branch",
        table_name="track_source_desempeno_daily",
    )
    op.drop_table("track_source_desempeno_daily")