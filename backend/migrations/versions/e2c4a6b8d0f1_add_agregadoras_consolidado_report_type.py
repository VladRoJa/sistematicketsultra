"""add agregadoras consolidado generated report type

Revision ID: e2c4a6b8d0f1
Revises: d8e4f2a6c1b9
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "e2c4a6b8d0f1"
down_revision = "d8e4f2a6c1b9"
branch_labels = None
depends_on = None


SOURCE_KEY = "suite_auto"
REPORT_TYPE_KEY = "agregadoras_consolidado"


def _fetch_required_id(connection, table_name: str, key: str) -> int:
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
            f"No existe el catálogo requerido {table_name}.key={key!r}."
        )

    return int(value)


def upgrade():
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            INSERT INTO warehouse_sources (
                key,
                label,
                active
            )
            VALUES (
                :key,
                :label,
                TRUE
            )
            ON CONFLICT (key)
            DO UPDATE SET
                label = EXCLUDED.label,
                active = TRUE
            """
        ),
        {
            "key": SOURCE_KEY,
            "label": "Suite Ultra Automático",
        },
    )

    family_id = _fetch_required_id(
        connection,
        "warehouse_families",
        "reportes_transaccionales",
    )
    source_id = _fetch_required_id(
        connection,
        "warehouse_sources",
        SOURCE_KEY,
    )
    role_id = _fetch_required_id(
        connection,
        "warehouse_operational_roles",
        "FUENTE_PRINCIPAL",
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
                'diario',
                TRUE
            )
            ON CONFLICT (key)
            DO UPDATE SET
                label = EXCLUDED.label,
                family_id = EXCLUDED.family_id,
                default_source_id = EXCLUDED.default_source_id,
                default_operational_role_id = EXCLUDED.default_operational_role_id,
                default_period_type = EXCLUDED.default_period_type,
                active = TRUE
            """
        ),
        {
            "key": REPORT_TYPE_KEY,
            "label": "Consolidado de Agregadoras",
            "family_id": family_id,
            "default_source_id": source_id,
            "default_operational_role_id": role_id,
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
            LIMIT 1
            """
        ),
        {"key": REPORT_TYPE_KEY},
    ).scalar()

    if report_type_id is not None:
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
        else:
            connection.execute(
                sa.text(
                    """
                    DELETE FROM warehouse_report_types
                    WHERE id = :id
                    """
                ),
                {"id": int(report_type_id)},
            )

    source_id = connection.execute(
        sa.text(
            """
            SELECT id
            FROM warehouse_sources
            WHERE key = :key
            LIMIT 1
            """
        ),
        {"key": SOURCE_KEY},
    ).scalar()

    if source_id is None:
        return

    report_type_usage = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM warehouse_report_types
            WHERE default_source_id = :source_id
            """
        ),
        {"source_id": int(source_id)},
    ).scalar()

    upload_usage = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM warehouse_uploads
            WHERE source_id = :source_id
            """
        ),
        {"source_id": int(source_id)},
    ).scalar()

    if int(report_type_usage or 0) == 0 and int(upload_usage or 0) == 0:
        connection.execute(
            sa.text(
                """
                DELETE FROM warehouse_sources
                WHERE id = :id
                """
            ),
            {"id": int(source_id)},
        )
