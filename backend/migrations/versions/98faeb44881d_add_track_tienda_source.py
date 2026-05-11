"""Add track tienda source

Revision ID: 98faeb44881d
Revises: 54d64c05b7b0
Create Date: 2026-05-11 06:21:54.854768

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '98faeb44881d'
down_revision = '54d64c05b7b0'
branch_labels = None
depends_on = None




def upgrade():
    op.create_table(
        "track_source_tienda_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("venta_tienda_mtd", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("source_report_type_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "business_date",
            "sucursal_canon",
            name="uq_track_source_tienda_daily_business_date_sucursal",
        ),
    )

    op.create_index(
        "ix_track_source_tienda_daily_business_date",
        "track_source_tienda_daily",
        ["business_date"],
    )

    op.add_column(
        "track_daily_mart",
        sa.Column("venta_tienda_real_mtd", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "track_daily_mart",
        sa.Column("source_snapshot_id_tienda", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "track_daily_mart",
        sa.Column("source_business_date_tienda", sa.Date(), nullable=True),
    )


def downgrade():
    op.drop_column("track_daily_mart", "source_business_date_tienda")
    op.drop_column("track_daily_mart", "source_snapshot_id_tienda")
    op.drop_column("track_daily_mart", "venta_tienda_real_mtd")

    op.drop_index(
        "ix_track_source_tienda_daily_business_date",
        table_name="track_source_tienda_daily",
    )
    op.drop_table("track_source_tienda_daily")