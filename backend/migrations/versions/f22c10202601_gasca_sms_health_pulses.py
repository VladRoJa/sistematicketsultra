"""Persist one health SMS pulse per two-hour UTC slot.

Revision ID: f22c10202601
Revises: d22c10202601
Create Date: 2026-10-20

No commercial SMS records are altered.
"""
from alembic import op
import sqlalchemy as sa

revision = "f22c10202601"
down_revision = "d22c10202601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gasca_sms_health_pulses",
        sa.Column("slot_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("slot_id", name="pk_gasca_sms_health_pulses"),
        sa.CheckConstraint(
            "status IN ('STARTED', 'SENT', 'FAILED')",
            name="ck_gasca_sms_health_pulse_status",
        ),
    )
    op.create_index(
        "ix_gasca_sms_health_pulse_attempt",
        "gasca_sms_health_pulses",
        ["attempted_at"],
    )


def downgrade():
    count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM gasca_sms_health_pulses")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "No es seguro borrar el historial de pulsos SMS sin respaldo."
        )
    op.drop_index(
        "ix_gasca_sms_health_pulse_attempt",
        table_name="gasca_sms_health_pulses",
    )
    op.drop_table("gasca_sms_health_pulses")
