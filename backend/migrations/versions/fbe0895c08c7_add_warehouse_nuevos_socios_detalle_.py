"""add warehouse nuevos socios detalle report type

Revision ID: fbe0895c08c7
Revises: afd781c27ea3
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "fbe0895c08c7"
down_revision = "afd781c27ea3"
branch_labels = None
depends_on = None


REPORT_TYPE_KEY = "ventas_nuevos_socios_detalle"
SOURCE_REPORT_TYPE_KEY = "kpi_ventas_nuevos_socios"


def upgrade():
    connection = op.get_bind()

    source_report_type = connection.execute(
        sa.text(
            """
            SELECT
                family_id,
                default_source_id,
                default_operational_role_id
            FROM warehouse_report_types
            WHERE key = :source_report_type_key
            """
        ),
        {
            "source_report_type_key": SOURCE_REPORT_TYPE_KEY,
        },
    ).mappings().first()

    if source_report_type is None:
        raise RuntimeError(
            "No existe el report type base "
            f"{SOURCE_REPORT_TYPE_KEY!r}; no se puede registrar "
            f"{REPORT_TYPE_KEY!r}."
        )

    required_fields = (
        "family_id",
        "default_source_id",
        "default_operational_role_id",
    )
    missing_fields = [
        field_name
        for field_name in required_fields
        if source_report_type[field_name] is None
    ]

    if missing_fields:
        raise RuntimeError(
            f"El report type base {SOURCE_REPORT_TYPE_KEY!r} "
            "no tiene configuración completa. "
            f"Campos faltantes: {', '.join(missing_fields)}."
        )

    connection.execute(
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
                :default_source_id,
                :default_operational_role_id,
                :default_period_type,
                TRUE
            )
            ON CONFLICT (key)
            DO UPDATE SET
                label = EXCLUDED.label,
                family_id = EXCLUDED.family_id,
                default_source_id = EXCLUDED.default_source_id,
                default_operational_role_id =
                    EXCLUDED.default_operational_role_id,
                default_period_type = EXCLUDED.default_period_type,
                active = TRUE
            """
        ),
        {
            "key": REPORT_TYPE_KEY,
            "label": "Ventas nuevos socios - detalle",
            "family_id": source_report_type["family_id"],
            "default_source_id": source_report_type["default_source_id"],
            "default_operational_role_id": (
                source_report_type["default_operational_role_id"]
            ),
            "default_period_type": "rango",
        },
    )


def downgrade():
    connection = op.get_bind()

    report_type_id = connection.execute(
        sa.text(
            """
            SELECT id
            FROM warehouse_report_types
            WHERE key = :key
            """
        ),
        {"key": REPORT_TYPE_KEY},
    ).scalar_one_or_none()

    if report_type_id is None:
        return

    upload_count = connection.execute(
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

    connection.execute(
        sa.text(
            """
            DELETE FROM warehouse_report_types
            WHERE id = :report_type_id
            """
        ),
        {"report_type_id": report_type_id},
    )
