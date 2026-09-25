"""add contact center appointment result events

Revision ID: cca2b3c4d5e6
Revises: cce1a2b3c4d5
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa


revision = "cca2b3c4d5e6"
down_revision = "cce1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_center_appointment_result_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("appointment_id", sa.BigInteger(), nullable=False),
        sa.Column("previous_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=False),
        sa.Column("previous_outcome", sa.String(length=50), nullable=True),
        sa.Column("new_outcome", sa.String(length=50), nullable=False),
        sa.Column("previous_case_status", sa.String(length=30), nullable=True),
        sa.Column("new_case_status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("venta_total_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("venta_total_snapshot_row_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('MANUAL_CORRECTION', 'VENTA_TOTAL_AUTO')",
            name="ck_contact_center_appt_result_event_source",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            ["contact_center_appointments.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["venta_total_snapshot_id"],
            ["venta_total_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["venta_total_snapshot_row_id"],
            ["venta_total_snapshot_rows.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contact_center_appt_result_event_appt_created",
        "contact_center_appointment_result_events",
        ["appointment_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_contact_center_appt_result_event_appt_created",
        table_name="contact_center_appointment_result_events",
    )
    op.drop_table("contact_center_appointment_result_events")
