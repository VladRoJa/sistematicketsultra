"""Tickets V1: tipo de atención y acciones explícitas de coordinación.

Revision ID: c17a10202601
Revises: b856rea1016
Create Date: 2026-10-17

Migración aditiva. La semántica de NULL es SIN_ASIGNAR para tickets legacy.
"""

from alembic import op
import sqlalchemy as sa


revision = "c17a10202601"
down_revision = "b856rea1016"
branch_labels = None
depends_on = None

ACTIONS = (
    (
        "maintenance.coordinate",
        "tickets.maintenance.coordinate",
        "Coordinar tickets de Mantenimiento",
        "Asignar responsable interno o proveedor externo y fecha compromiso.",
        "medium",
    ),
    (
        "maintenance.read_assigned_only",
        "tickets.maintenance.read_assigned_only",
        "Ver solo Mantenimiento asignado",
        "Restringe la bandeja de Mantenimiento del usuario a sus tickets asignados.",
        "low",
    ),
)


def upgrade():
    op.add_column(
        "tickets",
        sa.Column("tipo_atencion", sa.String(length=12), nullable=True),
    )
    op.create_check_constraint(
        "ck_tickets_tipo_atencion",
        "tickets",
        "tipo_atencion IS NULL OR tipo_atencion IN ('INTERNA', 'EXTERNA')",
    )

    connection = op.get_bind()
    # Tickets legacy asignados a usuarios son internos. Los demás permanecen
    # sin tipo; NULL no equivale automáticamente a proveedor.
    connection.execute(
        sa.text(
            "UPDATE tickets SET tipo_atencion = 'INTERNA' "
            "WHERE asignado_a IS NOT NULL"
        )
    )

    module_id = connection.execute(
        sa.text("SELECT id FROM permission_modules WHERE key = 'tickets'")
    ).scalar()
    if module_id is None:
        raise RuntimeError("No existe el módulo de permisos 'tickets'.")

    for key, full_key, name, description, risk_level in ACTIONS:
        existing = connection.execute(
            sa.text(
                "SELECT id FROM permission_actions WHERE full_key = :full_key"
            ),
            {"full_key": full_key},
        ).scalar()
        if existing is not None:
            continue

        connection.execute(
            sa.text(
                "INSERT INTO permission_actions "
                "(module_id, key, full_key, name, description, risk_level, is_active) "
                "VALUES (:module_id, :key, :full_key, :name, :description, "
                ":risk_level, TRUE)"
            ),
            {
                "module_id": module_id,
                "key": key,
                "full_key": full_key,
                "name": name,
                "description": description,
                "risk_level": risk_level,
            },
        )


def downgrade():
    connection = op.get_bind()
    keys = tuple(full_key for _, full_key, _, _, _ in ACTIONS)
    grant_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM permission_grants g "
            "JOIN permission_actions a ON a.id = g.action_id "
            "WHERE a.full_key IN (:first_key, :second_key)"
        ),
        {"first_key": keys[0], "second_key": keys[1]},
    ).scalar()
    if grant_count:
        raise RuntimeError(
            "No se puede revertir mientras existan grants de coordinación "
            "o de visibilidad asignada; revócalos de forma auditada primero."
        )

    connection.execute(
        sa.text(
            "DELETE FROM permission_actions "
            "WHERE full_key IN (:first_key, :second_key)"
        ),
        {"first_key": keys[0], "second_key": keys[1]},
    )
    op.drop_constraint(
        "ck_tickets_tipo_atencion", "tickets", type_="check"
    )
    op.drop_column("tickets", "tipo_atencion")
