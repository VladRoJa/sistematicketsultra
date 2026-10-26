"""E3: registrar acción de autorización sin conceder permisos.

Revision ID: v2e3a1102626
Revises: v2e3p2102626
Create Date: 2026-10-26

Solo alta de catálogo. No crea grants ni habilita endpoints o botones.
"""
from alembic import op
import sqlalchemy as sa


revision = "v2e3a1102626"
down_revision = "v2e3p2102626"
branch_labels = None
depends_on = None

ACTION = "inventory.correction_approve"


def upgrade():
    bind = op.get_bind()
    module_id = bind.execute(
        sa.text("SELECT id FROM permission_modules "
                "WHERE key = 'inventory' AND is_active IS TRUE")
    ).scalar_one_or_none()
    if module_id is None:
        raise RuntimeError("No existe el módulo inventory activo")

    existing = bind.execute(
        sa.text("SELECT id FROM permission_actions WHERE full_key = :action"),
        {"action": ACTION},
    ).scalar_one_or_none()
    if existing is not None:
        raise RuntimeError(
            "La acción inventory.correction_approve ya existe: revisar catálogo"
        )

    bind.execute(
        sa.text("""
            INSERT INTO permission_actions (
                module_id, key, full_key, name, description, risk_level,
                is_active, created_at, updated_at
            ) VALUES (
                :module_id, :key, :full_key, :name, :description,
                :risk_level, true, now(), now()
            )
        """),
        {
            "module_id": module_id,
            "key": "correction_approve",
            "full_key": ACTION,
            "name": "Autorizar correcciones de inventario",
            "description": (
                "Decisión formal de corrección E3: la aprobación aplica "
                "el cambio oficial y registra auditoría en una misma "
                "transacción. No concede acceso por sí misma."
            ),
            "risk_level": "critical",
        },
    )


def downgrade():
    bind = op.get_bind()
    action_id = bind.execute(
        sa.text("SELECT id FROM permission_actions WHERE full_key = :action"),
        {"action": ACTION},
    ).scalar_one_or_none()
    if action_id is None:
        return

    refs = [
        ("permission_grants", "action_id"),
        ("permission_route_map", "action_id"),
        ("permission_modules", "base_action_id"),
    ]
    for table, column in refs:
        used = bind.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE {column} = :id LIMIT 1"),
            {"id": action_id},
        ).scalar_one_or_none()
        if used is not None:
            raise RuntimeError(
                f"No se puede retirar {ACTION}: referenciada por {table}"
            )

    bind.execute(
        sa.text("DELETE FROM permission_actions "
                "WHERE id = :id AND full_key = :action"),
        {"id": action_id, "action": ACTION},
    )
