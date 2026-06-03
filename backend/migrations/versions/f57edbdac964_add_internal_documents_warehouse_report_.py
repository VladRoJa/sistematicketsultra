"""add internal documents warehouse report type

Revision ID: f57edbdac964
Revises: 45cb1ba3f367
Create Date: 2026-06-03 07:45:39.679797

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f57edbdac964"
down_revision = "45cb1ba3f367"
branch_labels = None
depends_on = None


INTERNAL_DOCUMENTS_REPORT_TYPE_KEY = "internal_documents"


def _fetch_id_by_key(connection, table_name: str, key: str) -> int:
    result = connection.execute(
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

    if result is None:
        raise RuntimeError(
            f"No existe el catálogo requerido {table_name}.key = {key!r}. "
            "No se puede crear el report_type de documentos internos."
        )

    return int(result)


def upgrade():
    connection = op.get_bind()

    manual_source_id = _fetch_id_by_key(
        connection,
        "warehouse_sources",
        "manual",
    )
    catalog_family_id = _fetch_id_by_key(
        connection,
        "warehouse_families",
        "catalogos_auxiliares",
    )
    catalog_role_id = _fetch_id_by_key(
        connection,
        "warehouse_operational_roles",
        "CATALOGO_AUXILIAR",
    )

    existing_report_type_id = connection.execute(
        sa.text(
            """
            SELECT id
            FROM warehouse_report_types
            WHERE key = :key
            LIMIT 1
            """
        ),
        {"key": INTERNAL_DOCUMENTS_REPORT_TYPE_KEY},
    ).scalar()

    if existing_report_type_id is not None:
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
                "id": int(existing_report_type_id),
                "label": "Documentos Internos",
                "family_id": catalog_family_id,
                "default_source_id": manual_source_id,
                "default_operational_role_id": catalog_role_id,
                "default_period_type": "diario",
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
        {
            "key": INTERNAL_DOCUMENTS_REPORT_TYPE_KEY,
            "label": "Documentos Internos",
            "family_id": catalog_family_id,
            "default_source_id": manual_source_id,
            "default_operational_role_id": catalog_role_id,
            "default_period_type": "diario",
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
        {"key": INTERNAL_DOCUMENTS_REPORT_TYPE_KEY},
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
    