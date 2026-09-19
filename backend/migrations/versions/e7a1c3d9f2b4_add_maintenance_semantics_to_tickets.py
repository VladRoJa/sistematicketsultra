"""add maintenance semantics to tickets

Revision ID: e7a1c3d9f2b4
Revises: c8f1d4a7e2b9
Create Date: 2026-09-18

Contrato:
docs/contratos/CONTRATO_TICKETS_MANTENIMIENTO_PREVENTIVO_V1.md
"""

from alembic import op
import sqlalchemy as sa


revision = "e7a1c3d9f2b4"
down_revision = "c8f1d4a7e2b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tickets",
        sa.Column("tipo_mantenimiento", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("origen_correctivo", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "fecha_compromiso_original",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "fecha_programada_original",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "fecha_programada_actual",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "fecha_validacion_cierre",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "ticket_preventivo_origen_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_tickets_tipo_mantenimiento",
        "tickets",
        "tipo_mantenimiento IS NULL "
        "OR tipo_mantenimiento IN ('CORRECTIVO', 'PREVENTIVO')",
    )
    op.create_check_constraint(
        "ck_tickets_origen_correctivo",
        "tickets",
        "origen_correctivo IS NULL "
        "OR origen_correctivo IN ('REACTIVO', 'DETECTADO_EN_PREVENTIVO')",
    )
    op.create_foreign_key(
        "fk_tickets_ticket_preventivo_origen",
        "tickets",
        "tickets",
        ["ticket_preventivo_origen_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_tickets_tipo_mantenimiento",
        "tickets",
        ["tipo_mantenimiento"],
        unique=False,
    )
    op.create_index(
        "ix_tickets_fecha_compromiso_original",
        "tickets",
        ["fecha_compromiso_original"],
        unique=False,
    )
    op.create_index(
        "ix_tickets_fecha_programada_actual",
        "tickets",
        ["fecha_programada_actual"],
        unique=False,
    )
    op.create_index(
        "ix_tickets_fecha_validacion_cierre",
        "tickets",
        ["fecha_validacion_cierre"],
        unique=False,
    )
    op.create_index(
        "ix_tickets_ticket_preventivo_origen_id",
        "tickets",
        ["ticket_preventivo_origen_id"],
        unique=False,
    )

    # Todo ticket histórico de Mantenimiento (depto 1) nació en el flujo
    # correctivo actual. No inventamos fechas originales para tickets ya
    # reprogramados: ese dato queda NULL si no puede probarse.
    op.execute(
        """
        UPDATE tickets
        SET tipo_mantenimiento = 'CORRECTIVO',
            origen_correctivo = 'REACTIVO'
        WHERE departamento_id = 1
          AND tipo_mantenimiento IS NULL
        """
    )

    # Cuando nunca existió historial de cambios sí es seguro considerar que el
    # compromiso vigente también fue el original.
    op.execute(
        """
        UPDATE tickets
        SET fecha_compromiso_original = fecha_solucion
        WHERE departamento_id = 1
          AND fecha_solucion IS NOT NULL
          AND historial_fechas IS NULL
          AND fecha_compromiso_original IS NULL
        """
    )


def downgrade():
    op.drop_index(
        "ix_tickets_ticket_preventivo_origen_id",
        table_name="tickets",
    )
    op.drop_index(
        "ix_tickets_fecha_validacion_cierre",
        table_name="tickets",
    )
    op.drop_index(
        "ix_tickets_fecha_programada_actual",
        table_name="tickets",
    )
    op.drop_index(
        "ix_tickets_fecha_compromiso_original",
        table_name="tickets",
    )
    op.drop_index(
        "ix_tickets_tipo_mantenimiento",
        table_name="tickets",
    )

    op.drop_constraint(
        "fk_tickets_ticket_preventivo_origen",
        "tickets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_tickets_origen_correctivo",
        "tickets",
        type_="check",
    )
    op.drop_constraint(
        "ck_tickets_tipo_mantenimiento",
        "tickets",
        type_="check",
    )

    op.drop_column("tickets", "ticket_preventivo_origen_id")
    op.drop_column("tickets", "fecha_validacion_cierre")
    op.drop_column("tickets", "fecha_programada_actual")
    op.drop_column("tickets", "fecha_programada_original")
    op.drop_column("tickets", "fecha_compromiso_original")
    op.drop_column("tickets", "origen_correctivo")
    op.drop_column("tickets", "tipo_mantenimiento")
