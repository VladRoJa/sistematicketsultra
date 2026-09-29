"""add agregadoras consolidado template report type

Revision ID: d8e4f2a6c1b9
Revises: c7d2e5f8a1b4
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "d8e4f2a6c1b9"
down_revision = "c7d2e5f8a1b4"
branch_labels = None
depends_on = None


REPORT_TYPE_KEY = "agregadoras_consolidado_template"


def _fetch_id_by_key(connection, table_name: str, key: str) -> int:
    value = connection.execute(
        sa.text(
            f"""
            SELECT id
            FROM {table_name}
            WHERE key = :key
            LIMIT 1
            """
        ),
        {"key": key},
    ).scalar()

    if value is None:
        raise RuntimeError(
            f"No existe {table_name}.key={key!r}; "
            "no se puede registrar la plantilla de agregadoras."
        )

    return int(value)


def upgrade():
    connection = op.get_bind()

    family_id = _fetch_id_by_key(
        connection,
        "warehouse_families",
        "catalogos_auxiliares",
    )
    source_id = _fetch_id_by_key(
        connection,
        "warehouse_sources",
        "manual",
    )
    role_id = _fetch_id_by_key(
        connection,
        "warehouse_operational_roles",
        "CATALOGO_AUXILIAR",
    )

    existing_id = connection.execute(
        sa.text(
            """
            SELECT id
            FROM warehouse_report_types
            WHERE key = :key
            LIMIT 1
            """
        ),
        {"key": REPORT_TYPE_KEY},
    ).scalar()

    values = {
        "key": REPORT_TYPE_KEY,
        "label": "Plantilla Consolidado Agregadoras",
        "family_id": family_id,
        "default_source_id": source_id,
        "default_operational_role_id": role_id,
        "default_period_type": "diario",
    }

    if existing_id is not None:
        connection.execute(
            sa.text(
                """
                UPDATE warehouse_report_types
                SET
                    label = :label,
                    family_id = :family_id,
                    default_source_id = :default_source_id,
                    default_operational_role_id = :default_operational_role_id,
                    default_period_type = :default_period_type,
                    active = TRUE
                WHERE id = :id
                """
            ),
            {
                **values,
                "id": int(existing_id),
            },
        )
        return

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
            """
        ),
        values,
    )


def downgrade():
    connection = op.get_bind()

    report_type_id = connection.execute(
        sa.text(
            """
            SELECT id
            FROM warehouse_report_types
            WHERE key = :key
            LIMIT 1
            """
        ),
        {"key": REPORT_TYPE_KEY},
    ).scalar()

    if report_type_id is None:
        return

    usage_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM warehouse_uploads
            WHERE report_type_id = :report_type_id
            """
        ),
        {"report_type_id": int(report_type_id)},
    ).scalar()

    if int(usage_count or 0) > 0:
        connection.execute(
            sa.text(
                """
                UPDATE warehouse_report_types
                SET active = FALSE
                WHERE id = :id
                """
            ),
            {"id": int(report_type_id)},
        )
        return

    connection.execute(
        sa.text(
            """
            DELETE FROM warehouse_report_types
            WHERE id = :id
            """
        ),
        {"id": int(report_type_id)},
    )
