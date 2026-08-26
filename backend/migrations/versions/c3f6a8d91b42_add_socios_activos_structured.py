"""add socios activos structured warehouse layer

Revision ID: c3f6a8d91b42
Revises: aab1ed1a5e31
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa


revision = "c3f6a8d91b42"
down_revision = "aab1ed1a5e31"
branch_labels = None
depends_on = None


REPORT_TYPE_KEY = "socios_activos"


def _get_id(bind, table_name: str, key: str) -> int:
    value = bind.execute(
        sa.text(
            f"SELECT id FROM {table_name} WHERE key = :key"
        ),
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
            "label": "Socios activos",
            "family_id": family_id,
            "source_id": source_id,
            "operational_role_id": operational_role_id,
            "period_type": "diario",
        },
    )


def upgrade():
    _register_report_type()

    op.create_table(
        "socios_activos_snapshots",
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
        sa.Column(
            "cutoff_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "snapshot_kind",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "is_canonical",
            sa.Boolean(),
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
        sa.ForeignKeyConstraint(
            ["warehouse_upload_id"],
            ["warehouse_uploads.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "warehouse_upload_id",
            name="uq_socios_activos_snapshots_upload",
        ),
    )

    op.create_index(
        "ix_socios_activos_snapshots_cutoff_date",
        "socios_activos_snapshots",
        ["cutoff_date"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_snapshots_captured_at",
        "socios_activos_snapshots",
        ["captured_at"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_snapshots_is_canonical",
        "socios_activos_snapshots",
        ["is_canonical"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_snapshots_cutoff_canonical",
        "socios_activos_snapshots",
        [
            "cutoff_date",
            "is_canonical",
        ],
        unique=False,
    )

    op.create_table(
        "socios_activos_snapshot_rows",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "row_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "source_row_number",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "id_socio",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "pin",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "nombre",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "sucursal_raw",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "fecha_ultimo_pago_local",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
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
            "fecha_ingreso_local",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
        sa.Column(
            "fecha_firma_local",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
        sa.Column(
            "tarifa",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "importe_tarifa",
            sa.Numeric(14, 2),
            nullable=True,
        ),
        sa.Column(
            "lada_raw",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column(
            "telefono_raw",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "telefono_digits",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column(
            "aplica_kpi_raw",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "aplica_kpi",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "email_raw",
            sa.String(length=320),
            nullable=True,
        ),
        sa.Column(
            "row_hash",
            sa.String(length=64),
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["socios_activos_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "row_index",
            name="uq_socios_activos_rows_snapshot_row_index",
        ),
    )

    op.create_index(
        "ix_socios_activos_rows_snapshot_id",
        "socios_activos_snapshot_rows",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_rows_id_socio",
        "socios_activos_snapshot_rows",
        ["id_socio"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_rows_pin",
        "socios_activos_snapshot_rows",
        ["pin"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_rows_branch",
        "socios_activos_snapshot_rows",
        ["sucursal_raw"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_rows_phone",
        "socios_activos_snapshot_rows",
        ["telefono_digits"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_rows_email",
        "socios_activos_snapshot_rows",
        ["email_raw"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_rows_expiration_date",
        "socios_activos_snapshot_rows",
        ["fecha_vencimiento_date"],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_rows_snapshot_member",
        "socios_activos_snapshot_rows",
        [
            "snapshot_id",
            "id_socio",
        ],
        unique=False,
    )
    op.create_index(
        "ix_socios_activos_rows_snapshot_branch_pin",
        "socios_activos_snapshot_rows",
        [
            "snapshot_id",
            "sucursal_raw",
            "pin",
        ],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_socios_activos_rows_snapshot_branch_pin",
        table_name="socios_activos_snapshot_rows",
    )
    op.drop_index(
        "ix_socios_activos_rows_snapshot_member",
        table_name="socios_activos_snapshot_rows",
    )
    op.drop_index(
        "ix_socios_activos_rows_expiration_date",
        table_name="socios_activos_snapshot_rows",
    )
    op.drop_index(
        "ix_socios_activos_rows_email",
        table_name="socios_activos_snapshot_rows",
    )
    op.drop_index(
        "ix_socios_activos_rows_phone",
        table_name="socios_activos_snapshot_rows",
    )
    op.drop_index(
        "ix_socios_activos_rows_branch",
        table_name="socios_activos_snapshot_rows",
    )
    op.drop_index(
        "ix_socios_activos_rows_pin",
        table_name="socios_activos_snapshot_rows",
    )
    op.drop_index(
        "ix_socios_activos_rows_id_socio",
        table_name="socios_activos_snapshot_rows",
    )
    op.drop_index(
        "ix_socios_activos_rows_snapshot_id",
        table_name="socios_activos_snapshot_rows",
    )

    op.drop_table(
        "socios_activos_snapshot_rows",
    )

    op.drop_index(
        "ix_socios_activos_snapshots_cutoff_canonical",
        table_name="socios_activos_snapshots",
    )
    op.drop_index(
        "ix_socios_activos_snapshots_is_canonical",
        table_name="socios_activos_snapshots",
    )
    op.drop_index(
        "ix_socios_activos_snapshots_captured_at",
        table_name="socios_activos_snapshots",
    )
    op.drop_index(
        "ix_socios_activos_snapshots_cutoff_date",
        table_name="socios_activos_snapshots",
    )

    op.drop_table(
        "socios_activos_snapshots",
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM warehouse_report_types
            WHERE key = :key
            """
        ),
        {"key": REPORT_TYPE_KEY},
    )
