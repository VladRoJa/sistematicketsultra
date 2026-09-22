"""add building preventive targets

Revision ID: a7c4e1f9b2d6
Revises: f6b0d4e8a2c7
Create Date: 2026-09-21

Edificio reutiliza catalogo_clasificacion, la fuente oficial del árbol
de Tickets. No se crea un catálogo paralelo.
"""

from alembic import op
import sqlalchemy as sa


revision = "a7c4e1f9b2d6"
down_revision = "f6b0d4e8a2c7"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # Programaciones recurrentes: EQUIPO o EDIFICIO.
    # ------------------------------------------------------------------
    op.add_column(
        "maintenance_preventive_schedules",
        sa.Column(
            "building_classification_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_maintenance_preventive_schedules_building_classification_id",
        "maintenance_preventive_schedules",
        "catalogo_clasificacion",
        ["building_classification_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_maintenance_preventive_schedules_building_classification_id",
        "maintenance_preventive_schedules",
        ["building_classification_id"],
        unique=False,
    )
    op.drop_constraint(
        "ck_maintenance_preventive_schedules_equipment_target",
        "maintenance_preventive_schedules",
        type_="check",
    )
    op.create_check_constraint(
        "ck_maintenance_preventive_schedules_target_reference",
        "maintenance_preventive_schedules",
        "((target_type = 'EQUIPO' AND inventario_id IS NOT NULL "
        "AND building_classification_id IS NULL) OR "
        "(target_type = 'EDIFICIO' AND inventario_id IS NULL "
        "AND building_classification_id IS NOT NULL))",
    )

    # ------------------------------------------------------------------
    # Renglones de planeación. Los campos *_input conservan el valor crudo
    # para poder mostrar/corregir errores sin perder la fila.
    # ------------------------------------------------------------------
    op.add_column(
        "maintenance_preventive_items",
        sa.Column("target_type_input", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "maintenance_preventive_items",
        sa.Column(
            "building_classification_input",
            sa.String(length=240),
            nullable=True,
        ),
    )
    op.add_column(
        "maintenance_preventive_items",
        sa.Column("target_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "maintenance_preventive_items",
        sa.Column(
            "building_classification_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_maintenance_preventive_items_building_classification_id",
        "maintenance_preventive_items",
        "catalogo_clasificacion",
        ["building_classification_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_maintenance_preventive_items_building_classification_id",
        "maintenance_preventive_items",
        ["building_classification_id"],
        unique=False,
    )

    # Todo renglón V1 previamente resuelto con inventario es, por definición,
    # un preventivo de equipo.
    op.execute(
        """
        UPDATE maintenance_preventive_items
        SET target_type = 'EQUIPO',
            target_type_input = COALESCE(target_type_input, 'EQUIPO')
        WHERE inventario_id IS NOT NULL
          AND target_type IS NULL
        """
    )
    op.create_check_constraint(
        "ck_maintenance_preventive_items_target_type",
        "maintenance_preventive_items",
        "target_type IS NULL OR target_type IN ('EQUIPO', 'EDIFICIO')",
    )
    op.create_check_constraint(
        "ck_maintenance_preventive_items_target_reference",
        "maintenance_preventive_items",
        "(validation_status <> 'VALIDO') OR "
        "((target_type = 'EQUIPO' AND inventario_id IS NOT NULL "
        "AND building_classification_id IS NULL) OR "
        "(target_type = 'EDIFICIO' AND inventario_id IS NULL "
        "AND building_classification_id IS NOT NULL))",
    )

    # ------------------------------------------------------------------
    # Ticket: discriminador explícito. Edificio reutiliza clasificacion_id.
    # ------------------------------------------------------------------
    op.add_column(
        "tickets",
        sa.Column(
            "maintenance_target_type",
            sa.String(length=20),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE tickets
        SET maintenance_target_type = 'EQUIPO'
        WHERE departamento_id = 1
          AND aparato_id IS NOT NULL
          AND maintenance_target_type IS NULL
        """
    )
    op.create_check_constraint(
        "ck_tickets_maintenance_target_type",
        "tickets",
        "maintenance_target_type IS NULL "
        "OR maintenance_target_type IN ('EQUIPO', 'EDIFICIO')",
    )
    op.create_check_constraint(
        "ck_tickets_maintenance_target_reference",
        "tickets",
        "maintenance_target_type IS NULL OR "
        "(maintenance_target_type = 'EQUIPO' AND aparato_id IS NOT NULL) OR "
        "(maintenance_target_type = 'EDIFICIO' AND aparato_id IS NULL "
        "AND clasificacion_id IS NOT NULL)",
    )
    op.create_index(
        "ix_tickets_maintenance_target_type",
        "tickets",
        ["maintenance_target_type"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # Bitácora: deja de asumir que todo preventivo tiene inventario.
    # ------------------------------------------------------------------
    op.add_column(
        "pm_bitacoras",
        sa.Column(
            "target_type",
            sa.String(length=20),
            server_default="EQUIPO",
            nullable=False,
        ),
    )
    op.add_column(
        "pm_bitacoras",
        sa.Column("clasificacion_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pm_bitacoras_clasificacion_id",
        "pm_bitacoras",
        "catalogo_clasificacion",
        ["clasificacion_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_pm_bitacoras_clasificacion_id",
        "pm_bitacoras",
        ["clasificacion_id"],
        unique=False,
    )
    op.alter_column(
        "pm_bitacoras",
        "inventario_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_pm_bitacoras_target_type",
        "pm_bitacoras",
        "target_type IN ('EQUIPO', 'EDIFICIO')",
    )
    op.create_check_constraint(
        "ck_pm_bitacoras_target_reference",
        "pm_bitacoras",
        "((target_type = 'EQUIPO' AND inventario_id IS NOT NULL "
        "AND clasificacion_id IS NULL) OR "
        "(target_type = 'EDIFICIO' AND inventario_id IS NULL "
        "AND clasificacion_id IS NOT NULL))",
    )


def downgrade():
    # No eliminamos datos de Edificio silenciosamente. Si ya existen bitácoras
    # de edificio, el downgrade debe detenerse antes de restaurar NOT NULL.
    op.execute(
        """
        DO $
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM maintenance_preventive_schedules
                WHERE target_type = 'EDIFICIO'
            ) OR EXISTS (
                SELECT 1
                FROM maintenance_preventive_items
                WHERE target_type = 'EDIFICIO'
            ) OR EXISTS (
                SELECT 1
                FROM tickets
                WHERE maintenance_target_type = 'EDIFICIO'
            ) OR EXISTS (
                SELECT 1
                FROM pm_bitacoras
                WHERE target_type = 'EDIFICIO'
                   OR inventario_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'No se puede revertir: existen datos PM de Edificio.';
            END IF;
        END $;
        """
    )

    op.drop_constraint(
        "ck_pm_bitacoras_target_reference",
        "pm_bitacoras",
        type_="check",
    )
    op.drop_constraint(
        "ck_pm_bitacoras_target_type",
        "pm_bitacoras",
        type_="check",
    )
    op.alter_column(
        "pm_bitacoras",
        "inventario_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_index(
        "ix_pm_bitacoras_clasificacion_id",
        table_name="pm_bitacoras",
    )
    op.drop_constraint(
        "fk_pm_bitacoras_clasificacion_id",
        "pm_bitacoras",
        type_="foreignkey",
    )
    op.drop_column("pm_bitacoras", "clasificacion_id")
    op.drop_column("pm_bitacoras", "target_type")

    op.drop_index(
        "ix_tickets_maintenance_target_type",
        table_name="tickets",
    )
    op.drop_constraint(
        "ck_tickets_maintenance_target_reference",
        "tickets",
        type_="check",
    )
    op.drop_constraint(
        "ck_tickets_maintenance_target_type",
        "tickets",
        type_="check",
    )
    op.drop_column("tickets", "maintenance_target_type")

    op.drop_constraint(
        "ck_maintenance_preventive_items_target_reference",
        "maintenance_preventive_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_maintenance_preventive_items_target_type",
        "maintenance_preventive_items",
        type_="check",
    )
    op.drop_index(
        "ix_maintenance_preventive_items_building_classification_id",
        table_name="maintenance_preventive_items",
    )
    op.drop_constraint(
        "fk_maintenance_preventive_items_building_classification_id",
        "maintenance_preventive_items",
        type_="foreignkey",
    )
    op.drop_column(
        "maintenance_preventive_items",
        "building_classification_id",
    )
    op.drop_column("maintenance_preventive_items", "target_type")
    op.drop_column(
        "maintenance_preventive_items",
        "building_classification_input",
    )
    op.drop_column("maintenance_preventive_items", "target_type_input")

    op.drop_constraint(
        "ck_maintenance_preventive_schedules_target_reference",
        "maintenance_preventive_schedules",
        type_="check",
    )
    op.create_check_constraint(
        "ck_maintenance_preventive_schedules_equipment_target",
        "maintenance_preventive_schedules",
        "target_type <> 'EQUIPO' OR inventario_id IS NOT NULL",
    )
    op.drop_index(
        "ix_maintenance_preventive_schedules_building_classification_id",
        table_name="maintenance_preventive_schedules",
    )
    op.drop_constraint(
        "fk_maintenance_preventive_schedules_building_classification_id",
        "maintenance_preventive_schedules",
        type_="foreignkey",
    )
    op.drop_column(
        "maintenance_preventive_schedules",
        "building_classification_id",
    )
