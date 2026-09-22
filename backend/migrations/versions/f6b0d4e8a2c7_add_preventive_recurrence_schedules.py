"""add preventive recurrence schedules

Revision ID: f6b0d4e8a2c7
Revises: e5a9c3d7f1b2
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa


revision = "f6b0d4e8a2c7"
down_revision = "e5a9c3d7f1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "maintenance_preventive_schedules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("schedule_key", sa.String(length=80), nullable=False),
        sa.Column(
            "target_type",
            sa.String(length=20),
            server_default="EQUIPO",
            nullable=False,
        ),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("inventario_id", sa.Integer(), nullable=True),
        sa.Column("responsable_user_id", sa.Integer(), nullable=True),
        sa.Column("actividad", sa.Text(), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("repeat_interval_workdays", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("next_scheduled_date", sa.Date(), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_type IN ('EQUIPO', 'EDIFICIO')",
            name="ck_maintenance_preventive_schedules_target_type",
        ),
        sa.CheckConstraint(
            "repeat_interval_workdays > 0",
            name="ck_maintenance_preventive_schedules_interval",
        ),
        sa.CheckConstraint(
            "target_type <> 'EQUIPO' OR inventario_id IS NOT NULL",
            name="ck_maintenance_preventive_schedules_equipment_target",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inventario_id"],
            ["inventario_general.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsable_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "schedule_key",
            name="uq_maintenance_preventive_schedules_schedule_key",
        ),
    )

    op.create_index(
        "ix_maintenance_preventive_schedules_sucursal_id",
        "maintenance_preventive_schedules",
        ["sucursal_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_schedules_inventario_id",
        "maintenance_preventive_schedules",
        ["inventario_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_schedules_responsable_user_id",
        "maintenance_preventive_schedules",
        ["responsable_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_schedules_created_by_user_id",
        "maintenance_preventive_schedules",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_schedules_next_scheduled_date",
        "maintenance_preventive_schedules",
        ["next_scheduled_date"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_preventive_schedules_active_next",
        "maintenance_preventive_schedules",
        ["active", "next_scheduled_date"],
        unique=False,
    )

    op.add_column(
        "maintenance_preventive_items",
        sa.Column(
            "repeat_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "maintenance_preventive_items",
        sa.Column("repeat_interval_workdays", sa.Integer(), nullable=True),
    )
    op.add_column(
        "maintenance_preventive_items",
        sa.Column("schedule_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_maintenance_preventive_items_schedule_id",
        "maintenance_preventive_items",
        "maintenance_preventive_schedules",
        ["schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_maintenance_preventive_items_schedule_id",
        "maintenance_preventive_items",
        ["schedule_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_maintenance_preventive_items_recurrence",
        "maintenance_preventive_items",
        "((repeat_enabled = false AND repeat_interval_workdays IS NULL) "
        "OR (repeat_enabled = true AND repeat_interval_workdays > 0))",
    )


def downgrade():
    op.drop_constraint(
        "ck_maintenance_preventive_items_recurrence",
        "maintenance_preventive_items",
        type_="check",
    )
    op.drop_index(
        "ix_maintenance_preventive_items_schedule_id",
        table_name="maintenance_preventive_items",
    )
    op.drop_constraint(
        "fk_maintenance_preventive_items_schedule_id",
        "maintenance_preventive_items",
        type_="foreignkey",
    )
    op.drop_column("maintenance_preventive_items", "schedule_id")
    op.drop_column(
        "maintenance_preventive_items",
        "repeat_interval_workdays",
    )
    op.drop_column("maintenance_preventive_items", "repeat_enabled")

    op.drop_index(
        "ix_maintenance_preventive_schedules_active_next",
        table_name="maintenance_preventive_schedules",
    )
    op.drop_index(
        "ix_maintenance_preventive_schedules_next_scheduled_date",
        table_name="maintenance_preventive_schedules",
    )
    op.drop_index(
        "ix_maintenance_preventive_schedules_created_by_user_id",
        table_name="maintenance_preventive_schedules",
    )
    op.drop_index(
        "ix_maintenance_preventive_schedules_responsable_user_id",
        table_name="maintenance_preventive_schedules",
    )
    op.drop_index(
        "ix_maintenance_preventive_schedules_inventario_id",
        table_name="maintenance_preventive_schedules",
    )
    op.drop_index(
        "ix_maintenance_preventive_schedules_sucursal_id",
        table_name="maintenance_preventive_schedules",
    )
    op.drop_table("maintenance_preventive_schedules")
