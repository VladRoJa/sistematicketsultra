"""create track venta total daily branch agg

Revision ID: 9a2b3c4d5e6f
Revises: 8f1e2d3c4b5a
Create Date: 2026-07-03

"""
from alembic import op
import sqlalchemy as sa


revision = "9a2b3c4d5e6f"
down_revision = "8f1e2d3c4b5a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "track_venta_total_daily_branch_agg",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("business_month", sa.Date(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("total", sa.Numeric(18, 2), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["venta_total_snapshots.id"],
            name="fk_track_vt_daily_branch_agg_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_track_vt_daily_branch_agg"),
        sa.UniqueConstraint(
            "snapshot_id",
            "sale_date",
            "sucursal_canon",
            name="uq_track_vt_daily_branch_agg_snapshot_date_branch",
        ),
    )

    op.create_index(
        "ix_track_vt_daily_branch_agg_snapshot_id",
        "track_venta_total_daily_branch_agg",
        ["snapshot_id"],
        unique=False,
    )

    op.create_index(
        "ix_track_vt_daily_branch_agg_month_day",
        "track_venta_total_daily_branch_agg",
        ["business_month", "day_of_month"],
        unique=False,
    )

    op.create_index(
        "ix_track_vt_daily_branch_agg_branch_month_day",
        "track_venta_total_daily_branch_agg",
        ["sucursal_canon", "business_month", "day_of_month"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_track_vt_daily_branch_agg_branch_month_day",
        table_name="track_venta_total_daily_branch_agg",
    )
    op.drop_index(
        "ix_track_vt_daily_branch_agg_month_day",
        table_name="track_venta_total_daily_branch_agg",
    )
    op.drop_index(
        "ix_track_vt_daily_branch_agg_snapshot_id",
        table_name="track_venta_total_daily_branch_agg",
    )
    op.drop_table("track_venta_total_daily_branch_agg")
