"""track_source_agregadoras_daily

Revision ID: ce2bc56fec0a
Revises: a42c792fa63c
Create Date: 2026-04-25 20:49:19.706728

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ce2bc56fec0a'
down_revision = 'a42c792fa63c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "track_source_agregadoras_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column(
            "ingreso_wellhub_mtd",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "ingreso_totalpass_mtd",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "ingreso_agregadora_total_mtd",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("source_snapshot_id_wellhub", sa.BigInteger(), nullable=True),
        sa.Column("source_snapshot_id_totalpass", sa.BigInteger(), nullable=True),
        sa.Column("source_report_type_key_wellhub", sa.Text(), nullable=True),
        sa.Column("source_report_type_key_totalpass", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_date",
            "sucursal_canon",
            name="uq_track_source_agregadoras_daily_business_date_branch",
        ),
    )

    op.create_index(
        "ix_track_source_agregadoras_daily_business_date",
        "track_source_agregadoras_daily",
        ["business_date"],
        unique=False,
    )

    op.create_index(
        "ix_track_source_agregadoras_daily_business_date_sucursal",
        "track_source_agregadoras_daily",
        ["business_date", "sucursal_canon"],
        unique=False,
    )

def downgrade():
    op.drop_index(
        "ix_track_source_agregadoras_daily_business_date_sucursal",
        table_name="track_source_agregadoras_daily",
    )

    op.drop_index(
        "ix_track_source_agregadoras_daily_business_date",
        table_name="track_source_agregadoras_daily",
    )

    op.drop_table("track_source_agregadoras_daily")