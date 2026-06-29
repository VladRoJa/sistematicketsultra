"""add permission module assignable metadata

Revision ID: 8f1e2d3c4b5a
Revises: 6a4d2c9e8f10
Create Date: 2026-06-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "8f1e2d3c4b5a"
down_revision = "6a4d2c9e8f10"
branch_labels = None
depends_on = None


VIEW_ACTIONS = [
    ("tickets", "view", "tickets.view", "Ver tickets", "Permite ver y entrar al módulo Tickets.", "low"),
    ("catalogs", "view", "catalogs.view", "Ver catálogos", "Permite ver y entrar al módulo Catálogos.", "low"),
    ("users", "view", "users.view", "Ver usuarios", "Permite ver y entrar al módulo Usuarios.", "high"),
]


MODULE_BASE_ACTIONS = [
    ("tickets", "tickets.view", "tickets", 10),
    ("inventory", "inventory.read", "inventory", 20),
    ("pm", "pm.read", "pm", 30),
    ("warehouse", "warehouse.view", "warehouse", 40),
    ("internal_documents", "internal_documents.view", "internal_documents", 50),
    ("track", "track.read", "track", 60),
    ("planning", "planning.read", "planning", 70),
    ("openings", "openings.read", "openings", 80),
    ("reports", "reports.read", "reports", 90),
    ("users", "users.view", "users", 100),
    ("catalogs", "catalogs.view", "catalogs", 110),
]


def upgrade():
    op.add_column(
        "permission_modules",
        sa.Column(
            "is_assignable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "permission_modules",
        sa.Column("menu_key", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "permission_modules",
        sa.Column(
            "sort_order",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "permission_modules",
        sa.Column("base_action_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_permission_modules_menu_key",
        "permission_modules",
        ["menu_key"],
        unique=False,
    )
    op.create_index(
        "ix_permission_modules_base_action_id",
        "permission_modules",
        ["base_action_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_permission_modules_base_action_id_permission_actions",
        "permission_modules",
        "permission_actions",
        ["base_action_id"],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()

    for module_key, action_key, full_key, name, description, risk_level in VIEW_ACTIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO permission_actions (
                    module_id,
                    key,
                    full_key,
                    name,
                    description,
                    risk_level,
                    is_active
                )
                SELECT
                    pm.id,
                    :action_key,
                    :full_key,
                    :name,
                    :description,
                    :risk_level,
                    true
                FROM permission_modules pm
                WHERE pm.key = :module_key
                  AND NOT EXISTS (
                      SELECT 1
                      FROM permission_actions pa
                      WHERE pa.full_key = :full_key
                  )
                """
            ),
            {
                "module_key": module_key,
                "action_key": action_key,
                "full_key": full_key,
                "name": name,
                "description": description,
                "risk_level": risk_level,
            },
        )

    for module_key, action_full_key, menu_key, sort_order in MODULE_BASE_ACTIONS:
        bind.execute(
            sa.text(
                """
                UPDATE permission_modules pm
                SET
                    is_assignable = true,
                    menu_key = :menu_key,
                    sort_order = :sort_order,
                    base_action_id = pa.id,
                    updated_at = now()
                FROM permission_actions pa
                WHERE pm.key = :module_key
                  AND pa.full_key = :action_full_key
                """
            ),
            {
                "module_key": module_key,
                "action_full_key": action_full_key,
                "menu_key": menu_key,
                "sort_order": sort_order,
            },
        )


def downgrade():
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            UPDATE permission_modules
            SET
                is_assignable = false,
                menu_key = NULL,
                sort_order = 0,
                base_action_id = NULL,
                updated_at = now()
            WHERE key IN (
                'tickets',
                'inventory',
                'pm',
                'warehouse',
                'internal_documents',
                'track',
                'planning',
                'openings',
                'reports',
                'users',
                'catalogs'
            )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            DELETE FROM permission_actions
            WHERE full_key IN (
                'tickets.view',
                'catalogs.view',
                'users.view'
            )
            """
        )
    )

    op.drop_constraint(
        "fk_permission_modules_base_action_id_permission_actions",
        "permission_modules",
        type_="foreignkey",
    )
    op.drop_index("ix_permission_modules_base_action_id", table_name="permission_modules")
    op.drop_index("ix_permission_modules_menu_key", table_name="permission_modules")

    op.drop_column("permission_modules", "base_action_id")
    op.drop_column("permission_modules", "sort_order")
    op.drop_column("permission_modules", "menu_key")
    op.drop_column("permission_modules", "is_assignable")
