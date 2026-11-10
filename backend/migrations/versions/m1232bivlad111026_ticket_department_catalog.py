"""Register BI Vlad department and its initial ticket classifications.

Revision ID: m1232bivlad111026
Revises: m1224tmpl110526
Create Date: 2026-11-10

This is a data-only migration. It does not assign users, grant permissions,
or authorize campaign dispatch.
"""

from alembic import op
import sqlalchemy as sa

revision = "m1232bivlad111026"
down_revision = "m1224tmpl110526"
branch_labels = None
depends_on = None

DEPARTMENT_NAME = "BI Vlad"
CATEGORY_NAMES = (
    "Campaña especial",
    "Reactivación de socios",
    "Segmentación de audiencia",
    "Idea o propuesta",
)


def _unique_existing_id(bind, query, params, label):
    matches = bind.execute(sa.text(query), params).scalars().all()
    if len(matches) > 1:
        raise RuntimeError(f"Hay múltiples registros para {label}; requiere revisión manual.")
    return matches[0] if matches else None


def _classification(bind, *, name, department_id, parent_id, level):
    sql = """
        SELECT id, nivel, activo
        FROM catalogo_clasificacion
        WHERE departamento_id = :department_id
          AND lower(trim(nombre)) = lower(trim(:name))
          AND parent_id IS NULL
    """ if parent_id is None else """
        SELECT id, nivel, activo
        FROM catalogo_clasificacion
        WHERE departamento_id = :department_id
          AND lower(trim(nombre)) = lower(trim(:name))
          AND parent_id = :parent_id
    """
    rows = bind.execute(sa.text(sql), {
        "department_id": department_id,
        "parent_id": parent_id,
        "name": name,
    }).mappings().all()
    if len(rows) > 1:
        raise RuntimeError(f"Clasificación duplicada en BI Vlad: {name}")
    if rows:
        row = rows[0]
        if int(row["nivel"]) != level or not row["activo"]:
            raise RuntimeError(f"Clasificación existente inconsistente/inactiva: {name}")
        return row["id"]
    return bind.execute(sa.text("""
        INSERT INTO catalogo_clasificacion
            (nombre, parent_id, departamento_id, nivel, activo)
        VALUES (:name, :parent_id, :department_id, :level, TRUE)
        RETURNING id
    """), {
        "name": name,
        "parent_id": parent_id,
        "department_id": department_id,
        "level": level,
    }).scalar_one()


def upgrade():
    bind = op.get_bind()
    department_id = _unique_existing_id(bind, """
        SELECT id FROM departamentos
        WHERE lower(trim(nombre)) = lower(trim(:name))
    """, {"name": DEPARTMENT_NAME}, "departamento BI Vlad")
    if department_id is None:
        department_id = bind.execute(sa.text("""
            INSERT INTO departamentos (nombre) VALUES (:name) RETURNING id
        """), {"name": DEPARTMENT_NAME}).scalar_one()

    root_id = _classification(
        bind, name=DEPARTMENT_NAME, department_id=department_id,
        parent_id=None, level=1,
    )
    for category in CATEGORY_NAMES:
        _classification(
            bind, name=category, department_id=department_id,
            parent_id=root_id, level=2,
        )


def downgrade():
    # These records may already be referenced by operational tickets, and
    # may have existed before the upgrade. Never delete business catalog data
    # (or reset an existing department) implicitly on a version rollback.
    raise RuntimeError(
        "BI Vlad es un catálogo operativo: reversión automática bloqueada "
        "para preservar tickets y clasificaciones."
    )
