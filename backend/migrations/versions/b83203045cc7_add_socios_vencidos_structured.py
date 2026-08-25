"""add socios vencidos structured warehouse layer

Revision ID: b83203045cc7
Revises: 7b2d9f4c6a81
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa


revision = "b83203045cc7"
down_revision = "7b2d9f4c6a81"
branch_labels = None
depends_on = None


REPORT_TYPE_KEY = "socios_vencidos"


def _get_id(bind, table_name: str, key: str) -> int:
    value = bind.execute(
        sa.text(f"SELECT id FROM {table_name} WHERE key = :key"),
        {"key": key},
    ).scalar_one_or_none()

    if value is None:
        raise RuntimeError(
            f"No existe {table_name}.{key!r}; no se puede registrar "
            f"{REPORT_TYPE_KEY!r}."
        )

    return int(value)


def _register_report_type() -> None:
    bind = op.get_bind()
    family_id = _get_id(
        bind,
        "warehouse_families",
        "reportes_transaccionales",
    )
    source_id = _get_id(
        bind,
        "warehouse_sources",
        "gasca",
    )
    operational_role_id = _get_id(
        bind,
        "warehouse_operational_roles",
        "FUENTE_PRINCIPAL",
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO warehouse_report_types (
                key,
                label,
                family_id,
                default_source_id,
                default_operational_role_id,
                default_period_type,
                active
            )
            VALUES (
                :key,
                :label,
                :family_id,
                :source_id,
                :operational_role_id,
                :period_type,
                TRUE
            )
            """
        ),
        {
            "key": REPORT_TYPE_KEY,
            "label": "Socios vencidos",
            "family_id": family_id,
            "source_id": source_id,
            "operational_role_id": operational_role_id,
            "period_type": "rango",
        },
    )


def upgrade():
    _register_report_type()

    op.create_table(
        "socios_vencidos_snapshots",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "warehouse_upload_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "report_type_key",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "row_count_detected",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "row_count_valid",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "row_count_rejected",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "date_from <= date_to",
            name="ck_socios_vencidos_snapshots_valid_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_upload_id"],
            ["warehouse_uploads.id"],
            name="fk_socios_vencidos_snapshots_warehouse_upload",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_socios_vencidos_snapshots",
        ),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_socios_vencidos_snapshots_warehouse_upload",
        ),
    )

    op.create_index(
        "ix_socios_vencidos_snapshots_date_from",
        "socios_vencidos_snapshots",
        ["date_from"],
        unique=False,
    )
    op.create_index(
        "ix_socios_vencidos_snapshots_date_to",
        "socios_vencidos_snapshots",
        ["date_to"],
        unique=False,
    )
    op.create_index(
        "ix_socios_vencidos_snapshots_captured_at",
        "socios_vencidos_snapshots",
        ["captured_at"],
        unique=False,
    )

    op.create_table(
        "socios_vencidos_snapshot_rows",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("pin", sa.String(length=64), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=True),
        sa.Column("genero", sa.String(length=50), nullable=True),
        sa.Column("edad", sa.Integer(), nullable=True),
        sa.Column(
            "fecha_vencimiento_local",
            sa.DateTime(timezone=False),
            nullable=False,
        ),
        sa.Column(
            "fecha_vencimiento_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "fecha_ultimo_pago_local",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
        sa.Column("tarifa", sa.String(length=255), nullable=True),
        sa.Column("correo_raw", sa.String(length=320), nullable=True),
        sa.Column("telefono_raw", sa.String(length=64), nullable=True),
        sa.Column("telefono_digits", sa.String(length=32), nullable=True),
        sa.Column("sucursal_raw", sa.String(length=255), nullable=False),
        sa.Column(
            "adeudo",
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["socios_vencidos_snapshots.id"],
            name="fk_socios_vencidos_rows_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_socios_vencidos_rows",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "row_index",
            name="uq_socios_vencidos_rows_snapshot_row_index",
        ),
    )

    row_indexes = (
        ("ix_socios_vencidos_rows_snapshot_id", ["snapshot_id"]),
        ("ix_socios_vencidos_rows_pin", ["pin"]),
        (
            "ix_socios_vencidos_rows_expiration_date",
            ["fecha_vencimiento_date"],
        ),
        ("ix_socios_vencidos_rows_branch", ["sucursal_raw"]),
        (
            "ix_socios_vencidos_rows_phone_digits",
            ["telefono_digits"],
        ),
        (
            "ix_socios_vencidos_rows_pin_expiration",
            ["pin", "fecha_vencimiento_date"],
        ),
        (
            "ix_socios_vencidos_rows_branch_expiration",
            ["sucursal_raw", "fecha_vencimiento_date"],
        ),
    )
    for index_name, columns in row_indexes:
        op.create_index(
            index_name,
            "socios_vencidos_snapshot_rows",
            columns,
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    report_type_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM warehouse_report_types
            WHERE key = :key
            """
        ),
        {"key": REPORT_TYPE_KEY},
    ).scalar_one_or_none()

    if report_type_id is not None:
        upload_count = bind.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM warehouse_uploads
                WHERE report_type_id = :report_type_id
                """
            ),
            {"report_type_id": report_type_id},
        ).scalar_one()
        if upload_count:
            raise RuntimeError(
                f"No se puede eliminar el report type {REPORT_TYPE_KEY!r}: "
                f"tiene {upload_count} upload(s) relacionado(s)."
            )

    row_indexes = (
        "ix_socios_vencidos_rows_branch_expiration",
        "ix_socios_vencidos_rows_pin_expiration",
        "ix_socios_vencidos_rows_phone_digits",
        "ix_socios_vencidos_rows_branch",
        "ix_socios_vencidos_rows_expiration_date",
        "ix_socios_vencidos_rows_pin",
        "ix_socios_vencidos_rows_snapshot_id",
    )
    for index_name in row_indexes:
        op.drop_index(
            index_name,
            table_name="socios_vencidos_snapshot_rows",
        )

    op.drop_table("socios_vencidos_snapshot_rows")

    snapshot_indexes = (
        "ix_socios_vencidos_snapshots_captured_at",
        "ix_socios_vencidos_snapshots_date_to",
        "ix_socios_vencidos_snapshots_date_from",
    )
    for index_name in snapshot_indexes:
        op.drop_index(
            index_name,
            table_name="socios_vencidos_snapshots",
        )

    op.drop_table("socios_vencidos_snapshots")

    if report_type_id is not None:
        bind.execute(
            sa.text(
                """
                DELETE FROM warehouse_report_types
                WHERE id = :report_type_id
                """
            ),
            {"report_type_id": report_type_id},
        )
