"""audita decisiones control rutinas

Revision ID: afd781c27ea3
Revises: 7d733d849a65
Create Date: 2026-07-26 14:39:39.906091
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "afd781c27ea3"
down_revision = "7d733d849a65"
branch_labels = None
depends_on = None


DECISION_REASON_CODES = (
    "NO_INTERESADO",
    "RUTINA_PROPIA",
    "ENTRENADOR_EXTERNO",
    "LIMITACION_MEDICA",
    "SOLO_CLASES_GRUPALES",
    "OTRO",
)


def upgrade():
    connection = op.get_bind()

    existing_decisions = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM routine_control_decisions
            """
        )
    ).scalar_one()

    if existing_decisions != 0:
        raise RuntimeError(
            "La migración afd781c27ea3 requiere que "
            "routine_control_decisions esté vacía para no inventar "
            "datos de auditoría históricos."
        )

    op.drop_constraint(
        "ck_routine_control_decisions_active_revocation",
        "routine_control_decisions",
        type_="check",
    )

    op.alter_column(
        "routine_control_decisions",
        "decision_reason",
        new_column_name="notes",
        existing_type=sa.Text(),
        existing_nullable=True,
    )

    op.add_column(
        "routine_control_decisions",
        sa.Column(
            "reason_code",
            sa.String(length=64),
            nullable=False,
        ),
    )
    op.add_column(
        "routine_control_decisions",
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            nullable=False,
        ),
    )
    op.add_column(
        "routine_control_decisions",
        sa.Column(
            "created_from_sucursal_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "routine_control_decisions",
        sa.Column(
            "revoked_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "routine_control_decisions",
        sa.Column(
            "revocation_reason",
            sa.Text(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_routine_control_decisions_created_by_user_id",
        "routine_control_decisions",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_routine_control_decisions_created_from_sucursal_id",
        "routine_control_decisions",
        "sucursales",
        ["created_from_sucursal_id"],
        ["sucursal_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_routine_control_decisions_revoked_by_user_id",
        "routine_control_decisions",
        "users",
        ["revoked_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    reason_codes_sql = ", ".join(
        f"'{reason_code}'"
        for reason_code in DECISION_REASON_CODES
    )

    op.create_check_constraint(
        "ck_routine_control_decisions_reason_code",
        "routine_control_decisions",
        f"reason_code IN ({reason_codes_sql})",
    )

    op.create_check_constraint(
        "ck_routine_control_decisions_other_requires_notes",
        "routine_control_decisions",
        """
        reason_code <> 'OTRO'
        OR NULLIF(BTRIM(notes), '') IS NOT NULL
        """,
    )

    op.create_check_constraint(
        "ck_routine_control_decisions_revocation_audit",
        "routine_control_decisions",
        """
        (
            is_active = true
            AND effective_to_utc IS NULL
            AND revoked_at_utc IS NULL
            AND revoked_by_user_id IS NULL
            AND revocation_reason IS NULL
        )
        OR
        (
            is_active = false
            AND effective_to_utc IS NOT NULL
            AND revoked_at_utc IS NOT NULL
            AND revoked_by_user_id IS NOT NULL
            AND NULLIF(BTRIM(revocation_reason), '') IS NOT NULL
        )
        """,
    )


def downgrade():
    op.drop_constraint(
        "ck_routine_control_decisions_revocation_audit",
        "routine_control_decisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_routine_control_decisions_other_requires_notes",
        "routine_control_decisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_routine_control_decisions_reason_code",
        "routine_control_decisions",
        type_="check",
    )

    op.drop_constraint(
        "fk_routine_control_decisions_revoked_by_user_id",
        "routine_control_decisions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_routine_control_decisions_created_from_sucursal_id",
        "routine_control_decisions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_routine_control_decisions_created_by_user_id",
        "routine_control_decisions",
        type_="foreignkey",
    )

    op.drop_column(
        "routine_control_decisions",
        "revocation_reason",
    )
    op.drop_column(
        "routine_control_decisions",
        "revoked_by_user_id",
    )
    op.drop_column(
        "routine_control_decisions",
        "created_from_sucursal_id",
    )
    op.drop_column(
        "routine_control_decisions",
        "created_by_user_id",
    )
    op.drop_column(
        "routine_control_decisions",
        "reason_code",
    )

    op.alter_column(
        "routine_control_decisions",
        "notes",
        new_column_name="decision_reason",
        existing_type=sa.Text(),
        existing_nullable=True,
    )

    op.create_check_constraint(
        "ck_routine_control_decisions_active_revocation",
        "routine_control_decisions",
        "is_active = false OR revoked_at_utc IS NULL",
    )