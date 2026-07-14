"""add routine control incidents and decisions

Revision ID: c2a4e8f91b7d
Revises: f6740e2f5d25
Create Date: 2026-07-14 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c2a4e8f91b7d"
down_revision = "f6740e2f5d25"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "routine_control_incidents",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "incident_type",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "is_blocking",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "detected_at_utc",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "resolved_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "resolution_note",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            """
            incident_type IN (
                'EMAIL_VACIO',
                'EMAIL_DUPLICADO_GASCA',
                'COINCIDENCIA_AMBIGUA',
                'SUCURSAL_NO_RESUELTA',
                'FECHA_VENTA_INVALIDA',
                'COHORTE_NO_DETERMINADA',
                'REGISTRO_ORIGEN_INVALIDO'
            )
            """,
            name="ck_routine_control_incidents_incident_type",
        ),
        sa.CheckConstraint(
            "is_active = false OR resolved_at_utc IS NULL",
            name="ck_routine_control_incidents_active_resolution",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["routine_control_members.id"],
            name="fk_routine_control_incidents_member_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_routine_control_incidents",
        ),
    )
    op.create_index(
        "ix_routine_control_incidents_member_active_blocking",
        "routine_control_incidents",
        ["member_id", "is_active", "is_blocking"],
        unique=False,
    )
    op.create_index(
        "uq_routine_control_incidents_active_member_type",
        "routine_control_incidents",
        ["member_id", "incident_type"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "routine_control_decisions",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "decision_type",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "decided_at_utc",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "effective_from_utc",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "effective_to_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "decision_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision_type IN ('NO_DESEA_RUTINA')",
            name="ck_routine_control_decisions_decision_type",
        ),
        sa.CheckConstraint(
            """
            effective_to_utc IS NULL
            OR effective_to_utc > effective_from_utc
            """,
            name="ck_routine_control_decisions_effective_range",
        ),
        sa.CheckConstraint(
            "is_active = false OR revoked_at_utc IS NULL",
            name="ck_routine_control_decisions_active_revocation",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["routine_control_members.id"],
            name="fk_routine_control_decisions_member_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_routine_control_decisions",
        ),
    )
    op.create_index(
        "ix_routine_control_decisions_member_type_active",
        "routine_control_decisions",
        ["member_id", "decision_type", "is_active"],
        unique=False,
    )
    op.create_index(
        "uq_routine_control_decisions_active_member_type",
        "routine_control_decisions",
        ["member_id", "decision_type"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade():
    op.drop_index(
        "uq_routine_control_decisions_active_member_type",
        table_name="routine_control_decisions",
    )
    op.drop_index(
        "ix_routine_control_decisions_member_type_active",
        table_name="routine_control_decisions",
    )
    op.drop_table("routine_control_decisions")

    op.drop_index(
        "uq_routine_control_incidents_active_member_type",
        table_name="routine_control_incidents",
    )
    op.drop_index(
        "ix_routine_control_incidents_member_active_blocking",
        table_name="routine_control_incidents",
    )
    op.drop_table("routine_control_incidents")
