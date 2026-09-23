"""create contact center v1

Revision ID: cce1a2b3c4d5
Revises: c8f1d4a7e2b9
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa


revision = "cce1a2b3c4d5"
down_revision = "c8f1d4a7e2b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_center_contacts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("primary_phone_raw", sa.String(length=100), nullable=False),
        sa.Column("phone_mx10", sa.String(length=10), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("preferred_sucursal_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("merged_into_contact_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["preferred_sucursal_id"],
            ["sucursales.sucursal_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_contact_id"],
            ["contact_center_contacts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contact_center_contacts_phone_mx10",
        "contact_center_contacts",
        ["phone_mx10"],
    )
    op.create_index(
        "ix_contact_center_contacts_email",
        "contact_center_contacts",
        ["email"],
    )
    op.create_index(
        "ix_contact_center_contacts_active",
        "contact_center_contacts",
        ["is_active"],
    )

    op.create_table(
        "contact_center_contact_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("source_row_id", sa.BigInteger(), nullable=True),
        sa.Column("source_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('IVENTAS_CONTACT', 'REACTIVATION_RECIPIENT', 'MARKETING_CAMPAIGN', 'MESSAGE', 'MANUAL')",
            name="ck_contact_center_links_source_type",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contact_center_contacts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_key",
            name="uq_contact_center_links_source",
        ),
    )
    op.create_index(
        "ix_contact_center_links_contact_id",
        "contact_center_contact_links",
        ["contact_id"],
    )

    op.create_table(
        "contact_center_cases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("sucursal_id", sa.Integer(), nullable=True),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="NEW", nullable=False),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('CRM', 'MESSAGE', 'REACTIVATION', 'CAMPAIGN', 'MANUAL')",
            name="ck_contact_center_cases_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('NEW', 'IN_PROGRESS', 'FOLLOW_UP', 'APPOINTMENT', 'CLOSED')",
            name="ck_contact_center_cases_status",
        ),
        sa.ForeignKeyConstraint(["contact_id"], ["contact_center_contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sucursal_id"], ["sucursales.sucursal_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contact_center_cases_assignee_status",
        "contact_center_cases",
        ["assigned_user_id", "status"],
    )
    op.create_index(
        "ix_contact_center_cases_contact_id",
        "contact_center_cases",
        ["contact_id"],
    )
    op.create_index(
        "ix_contact_center_cases_next_action_at",
        "contact_center_cases",
        ["next_action_at"],
    )
    op.create_index(
        "ix_contact_center_cases_sucursal_id",
        "contact_center_cases",
        ["sucursal_id"],
    )

    op.create_table(
        "contact_center_interactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("interaction_type", sa.String(length=30), server_default="CALL", nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "interaction_type IN ('CALL', 'MESSAGE', 'NOTE', 'SYSTEM')",
            name="ck_contact_center_interactions_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('NO_ANSWER', 'CALL_BACK', 'INTERESTED', 'APPOINTMENT', 'NOT_INTERESTED', 'WRONG_NUMBER', 'DO_NOT_CONTACT', 'NOTE')",
            name="ck_contact_center_interactions_outcome",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["contact_center_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contact_center_contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contact_center_interactions_case_created",
        "contact_center_interactions",
        ["case_id", "created_at"],
    )
    op.create_index(
        "ix_contact_center_interactions_contact_id",
        "contact_center_interactions",
        ["contact_id"],
    )

    op.create_table(
        "contact_center_appointments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="America/Tijuana", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="SCHEDULED", nullable=False),
        sa.Column("outcome", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rescheduled_to_appointment_id", sa.BigInteger(), nullable=True),
        sa.Column("purchase_reported", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("purchase_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purchase_reported_by_user_id", sa.Integer(), nullable=True),
        sa.Column("purchase_verification_status", sa.String(length=30), server_default="NOT_REPORTED", nullable=False),
        sa.Column("venta_total_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("venta_total_snapshot_row_id", sa.Integer(), nullable=True),
        sa.Column("verified_purchase_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("verified_tariff", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('SCHEDULED', 'CANCELLED', 'RESCHEDULED', 'CLOSED')",
            name="ck_contact_center_appointments_status",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('ATTENDED_PURCHASE_REPORTED', 'ATTENDED_NO_PURCHASE', 'NO_SHOW', 'CANCELLED', 'RESCHEDULED')",
            name="ck_contact_center_appointments_outcome",
        ),
        sa.CheckConstraint(
            "purchase_verification_status IN ('NOT_REPORTED', 'REPORTED_PENDING', 'VERIFIED', 'REVIEW', 'NOT_FOUND_YET')",
            name="ck_contact_center_appointments_purchase_verification",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["contact_center_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contact_id"], ["contact_center_contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sucursal_id"], ["sucursales.sucursal_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["purchase_reported_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rescheduled_to_appointment_id"], ["contact_center_appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["venta_total_snapshot_id"], ["venta_total_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["venta_total_snapshot_row_id"], ["venta_total_snapshot_rows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contact_center_appointments_branch_scheduled",
        "contact_center_appointments",
        ["sucursal_id", "scheduled_at"],
    )
    op.create_index(
        "ix_contact_center_appointments_status_scheduled",
        "contact_center_appointments",
        ["status", "scheduled_at"],
    )
    op.create_index(
        "ix_contact_center_appointments_contact_id",
        "contact_center_appointments",
        ["contact_id"],
    )
    op.create_index(
        "ix_contact_center_appointments_case_id",
        "contact_center_appointments",
        ["case_id"],
    )

    op.create_table(
        "contact_center_contact_merge_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("survivor_contact_id", sa.BigInteger(), nullable=False),
        sa.Column("merged_contact_id", sa.BigInteger(), nullable=False),
        sa.Column("field_resolution_json", sa.JSON(), nullable=False),
        sa.Column("merged_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "survivor_contact_id <> merged_contact_id",
            name="ck_contact_center_merge_distinct_contacts",
        ),
        sa.ForeignKeyConstraint(["survivor_contact_id"], ["contact_center_contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["merged_contact_id"], ["contact_center_contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["merged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contact_center_merge_survivor",
        "contact_center_contact_merge_events",
        ["survivor_contact_id"],
    )
    op.create_index(
        "ix_contact_center_merge_merged",
        "contact_center_contact_merge_events",
        ["merged_contact_id"],
    )

    op.create_table(
        "contact_center_notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("appointment_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("recipients_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')",
            name="ck_contact_center_notifications_status",
        ),
        sa.ForeignKeyConstraint(["appointment_id"], ["contact_center_appointments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contact_center_notifications_appointment",
        "contact_center_notifications",
        ["appointment_id", "created_at"],
    )


def downgrade():
    op.drop_index(
        "ix_contact_center_notifications_appointment",
        table_name="contact_center_notifications",
    )
    op.drop_table("contact_center_notifications")

    op.drop_index(
        "ix_contact_center_merge_merged",
        table_name="contact_center_contact_merge_events",
    )
    op.drop_index(
        "ix_contact_center_merge_survivor",
        table_name="contact_center_contact_merge_events",
    )
    op.drop_table("contact_center_contact_merge_events")

    op.drop_index(
        "ix_contact_center_appointments_case_id",
        table_name="contact_center_appointments",
    )
    op.drop_index(
        "ix_contact_center_appointments_contact_id",
        table_name="contact_center_appointments",
    )
    op.drop_index(
        "ix_contact_center_appointments_status_scheduled",
        table_name="contact_center_appointments",
    )
    op.drop_index(
        "ix_contact_center_appointments_branch_scheduled",
        table_name="contact_center_appointments",
    )
    op.drop_table("contact_center_appointments")

    op.drop_index(
        "ix_contact_center_interactions_contact_id",
        table_name="contact_center_interactions",
    )
    op.drop_index(
        "ix_contact_center_interactions_case_created",
        table_name="contact_center_interactions",
    )
    op.drop_table("contact_center_interactions")

    op.drop_index(
        "ix_contact_center_cases_sucursal_id",
        table_name="contact_center_cases",
    )
    op.drop_index(
        "ix_contact_center_cases_next_action_at",
        table_name="contact_center_cases",
    )
    op.drop_index(
        "ix_contact_center_cases_contact_id",
        table_name="contact_center_cases",
    )
    op.drop_index(
        "ix_contact_center_cases_assignee_status",
        table_name="contact_center_cases",
    )
    op.drop_table("contact_center_cases")

    op.drop_index(
        "ix_contact_center_links_contact_id",
        table_name="contact_center_contact_links",
    )
    op.drop_table("contact_center_contact_links")

    op.drop_index(
        "ix_contact_center_contacts_active",
        table_name="contact_center_contacts",
    )
    op.drop_index(
        "ix_contact_center_contacts_email",
        table_name="contact_center_contacts",
    )
    op.drop_index(
        "ix_contact_center_contacts_phone_mx10",
        table_name="contact_center_contacts",
    )
    op.drop_table("contact_center_contacts")
