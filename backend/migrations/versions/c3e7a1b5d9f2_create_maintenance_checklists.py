"""create configurable maintenance checklists

Revision ID: c3e7a1b5d9f2
Revises: b2d6f8a1c3e5
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "c3e7a1b5d9f2"
down_revision = "b2d6f8a1c3e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "maintenance_checklist_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("familia_equipo_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("actividad_key", sa.String(length=180), nullable=True),
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["familia_equipo_id"],
            ["familia_equipo.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_key",
            name="uq_maintenance_checklist_templates_template_key",
        ),
    )
    op.create_index(
        "ix_maintenance_checklist_templates_familia_equipo_id",
        "maintenance_checklist_templates",
        ["familia_equipo_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_checklist_templates_family_active",
        "maintenance_checklist_templates",
        ["familia_equipo_id", "activo"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_checklist_templates_activity",
        "maintenance_checklist_templates",
        ["familia_equipo_id", "actividad_key"],
        unique=False,
    )

    op.create_table(
        "maintenance_checklist_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("item_key", sa.String(length=100), nullable=False),
        sa.Column("etiqueta", sa.String(length=220), nullable=False),
        sa.Column(
            "orden",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "requerido",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["maintenance_checklist_templates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "item_key",
            name="uq_maintenance_checklist_item_key",
        ),
    )
    op.create_index(
        "ix_maintenance_checklist_items_template_id",
        "maintenance_checklist_items",
        ["template_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_checklist_items_template_active_order",
        "maintenance_checklist_items",
        ["template_id", "activo", "orden"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_maintenance_checklist_items_template_active_order",
        table_name="maintenance_checklist_items",
    )
    op.drop_index(
        "ix_maintenance_checklist_items_template_id",
        table_name="maintenance_checklist_items",
    )
    op.drop_table("maintenance_checklist_items")

    op.drop_index(
        "ix_maintenance_checklist_templates_activity",
        table_name="maintenance_checklist_templates",
    )
    op.drop_index(
        "ix_maintenance_checklist_templates_family_active",
        table_name="maintenance_checklist_templates",
    )
    op.drop_index(
        "ix_maintenance_checklist_templates_familia_equipo_id",
        table_name="maintenance_checklist_templates",
    )
    op.drop_table("maintenance_checklist_templates")
