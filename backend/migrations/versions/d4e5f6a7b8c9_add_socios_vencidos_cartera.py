"""add socios vencidos persistent cartera

Revision ID: d4e5f6a7b8c9
Revises: c3f6a8d91b42
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3f6a8d91b42"
branch_labels = None
depends_on = None


EDAD_QUALITY_CHECK = (
    "(edad_status = 'VALID' "
    "AND edad_raw BETWEEN 0 AND 120 "
    "AND edad = edad_raw) "
    "OR (edad_status = 'INVALID_OUT_OF_RANGE' "
    "AND edad_raw IS NOT NULL "
    "AND (edad_raw < 0 OR edad_raw > 120) "
    "AND edad IS NULL) "
    "OR (edad_status = 'MISSING' "
    "AND edad_raw IS NULL "
    "AND edad IS NULL)"
)


def upgrade():
    op.add_column(
        "warehouse_uploads",
        sa.Column(
            "source_file_deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "socios_vencidos_snapshots",
        sa.Column(
            "row_storage_mode",
            sa.String(length=32),
            nullable=False,
            server_default="SNAPSHOT_ONLY",
        ),
    )
    for column_name in (
        "cartera_inserted_count",
        "cartera_updated_count",
        "cartera_existing_count",
    ):
        op.add_column(
            "socios_vencidos_snapshots",
            sa.Column(
                column_name,
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    op.create_check_constraint(
        "ck_socios_vencidos_snapshots_row_storage_mode",
        "socios_vencidos_snapshots",
        "row_storage_mode IN ('SNAPSHOT_ONLY', 'CARTERA_ONLY')",
    )
    op.create_check_constraint(
        "ck_socios_vencidos_snapshots_cartera_counts",
        "socios_vencidos_snapshots",
        "cartera_inserted_count >= 0 "
        "AND cartera_updated_count >= 0 "
        "AND cartera_existing_count >= 0",
    )

    op.create_table(
        "socios_vencidos_cartera",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sucursal_raw", sa.String(length=255), nullable=False),
        sa.Column("sucursal_key", sa.String(length=255), nullable=False),
        sa.Column("pin", sa.String(length=64), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=True),
        sa.Column("genero", sa.String(length=50), nullable=True),
        sa.Column("edad_raw", sa.Integer(), nullable=True),
        sa.Column("edad", sa.Integer(), nullable=True),
        sa.Column("edad_status", sa.String(length=32), nullable=False),
        sa.Column(
            "fecha_vencimiento_local",
            sa.DateTime(timezone=False),
            nullable=False,
        ),
        sa.Column("fecha_vencimiento_date", sa.Date(), nullable=False),
        sa.Column(
            "fecha_ultimo_pago_local",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
        sa.Column("tarifa", sa.String(length=255), nullable=True),
        sa.Column("correo_raw", sa.String(length=320), nullable=True),
        sa.Column("telefono_raw", sa.String(length=64), nullable=True),
        sa.Column("telefono_digits", sa.String(length=32), nullable=True),
        sa.Column("adeudo", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("first_source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("last_source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            EDAD_QUALITY_CHECK,
            name="ck_socios_vencidos_cartera_edad_quality",
        ),
        sa.CheckConstraint(
            "first_seen_at <= last_seen_at",
            name="ck_socios_vencidos_cartera_seen_range",
        ),
        sa.ForeignKeyConstraint(
            ["first_source_snapshot_id"],
            ["socios_vencidos_snapshots.id"],
            name="fk_socios_vencidos_cartera_first_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_source_snapshot_id"],
            ["socios_vencidos_snapshots.id"],
            name="fk_socios_vencidos_cartera_last_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_socios_vencidos_cartera"),
        sa.UniqueConstraint(
            "sucursal_key",
            "pin",
            "fecha_vencimiento_date",
            name="uq_socios_vencidos_cartera_episode",
        ),
    )

    indexes = (
        ("ix_socios_vencidos_cartera_expiration_date", ["fecha_vencimiento_date"]),
        (
            "ix_socios_vencidos_cartera_branch_expiration",
            ["sucursal_key", "fecha_vencimiento_date"],
        ),
        ("ix_socios_vencidos_cartera_pin", ["pin"]),
        ("ix_socios_vencidos_cartera_phone_digits", ["telefono_digits"]),
    )
    for index_name, columns in indexes:
        op.create_index(
            index_name,
            "socios_vencidos_cartera",
            columns,
            unique=False,
        )


def downgrade():
    for index_name in (
        "ix_socios_vencidos_cartera_phone_digits",
        "ix_socios_vencidos_cartera_pin",
        "ix_socios_vencidos_cartera_branch_expiration",
        "ix_socios_vencidos_cartera_expiration_date",
    ):
        op.drop_index(index_name, table_name="socios_vencidos_cartera")

    op.drop_table("socios_vencidos_cartera")
    op.drop_constraint(
        "ck_socios_vencidos_snapshots_cartera_counts",
        "socios_vencidos_snapshots",
        type_="check",
    )
    op.drop_constraint(
        "ck_socios_vencidos_snapshots_row_storage_mode",
        "socios_vencidos_snapshots",
        type_="check",
    )
    for column_name in (
        "cartera_existing_count",
        "cartera_updated_count",
        "cartera_inserted_count",
        "row_storage_mode",
    ):
        op.drop_column("socios_vencidos_snapshots", column_name)

    op.drop_column("warehouse_uploads", "source_file_deleted_at")
