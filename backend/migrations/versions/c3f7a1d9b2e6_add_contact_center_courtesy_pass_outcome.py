"""add contact center courtesy pass outcome

Revision ID: c3f7a1d9b2e6
Revises: e8b4c1d7a2f9
Create Date: 2026-10-03
"""

from alembic import op
import sqlalchemy as sa


revision = "c3f7a1d9b2e6"
down_revision = "e8b4c1d7a2f9"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_contact_center_appointments_outcome",
        "contact_center_appointments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_contact_center_appointments_outcome",
        "contact_center_appointments",
        "outcome IS NULL OR outcome IN ("
        "'ATTENDED_PURCHASE_REPORTED', "
        "'ATTENDED_NO_PURCHASE', "
        "'ATTENDED_COURTESY_PASS', "
        "'NO_SHOW', "
        "'CANCELLED', "
        "'RESCHEDULED'"
        ")",
    )

    op.execute(
        sa.text(
            """
            WITH targets AS (
                SELECT
                    appointment.id AS appointment_id,
                    appointment.case_id AS case_id,
                    appointment.status AS previous_status,
                    appointment.outcome AS previous_outcome,
                    case_row.status AS previous_case_status,
                    appointment.venta_total_snapshot_id AS snapshot_id,
                    appointment.venta_total_snapshot_row_id AS snapshot_row_id
                FROM contact_center_appointments AS appointment
                JOIN contact_center_cases AS case_row
                  ON case_row.id = appointment.case_id
                WHERE appointment.purchase_verification_status = 'VERIFIED'
                  AND COALESCE(appointment.verified_amount, 0) <= 0
            ),
            event_insert AS (
                INSERT INTO contact_center_appointment_result_events (
                    appointment_id,
                    previous_status,
                    new_status,
                    previous_outcome,
                    new_outcome,
                    previous_case_status,
                    new_case_status,
                    source,
                    changed_by_user_id,
                    venta_total_snapshot_id,
                    venta_total_snapshot_row_id,
                    reason,
                    created_at
                )
                SELECT
                    appointment_id,
                    previous_status,
                    'CLOSED',
                    previous_outcome,
                    'ATTENDED_COURTESY_PASS',
                    previous_case_status,
                    'IN_PROGRESS',
                    'VENTA_TOTAL_AUTO',
                    NULL,
                    snapshot_id,
                    snapshot_row_id,
                    'Correccion historica: una operacion con importe no positivo no representa una compra real.',
                    NOW()
                FROM targets
                RETURNING appointment_id
            ),
            appointment_update AS (
                UPDATE contact_center_appointments AS appointment
                SET
                    status = 'CLOSED',
                    outcome = 'ATTENDED_COURTESY_PASS',
                    closed_by_user_id = NULL,
                    purchase_reported = FALSE,
                    purchase_reported_at = NULL,
                    purchase_reported_by_user_id = NULL,
                    purchase_verification_status = 'NOT_REPORTED',
                    venta_total_snapshot_id = NULL,
                    venta_total_snapshot_row_id = NULL,
                    verified_purchase_at = NULL,
                    verified_amount = NULL,
                    verified_tariff = NULL,
                    updated_at = NOW()
                WHERE appointment.id IN (
                    SELECT appointment_id FROM targets
                )
                RETURNING appointment.case_id
            )
            UPDATE contact_center_cases AS case_row
            SET
                status = 'IN_PROGRESS',
                next_action_at = NULL,
                closed_at = NULL,
                closed_by_user_id = NULL,
                updated_at = NOW()
            WHERE case_row.id IN (
                SELECT case_id FROM appointment_update
            )
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            "UPDATE contact_center_appointments "
            "SET outcome = 'ATTENDED_NO_PURCHASE' "
            "WHERE outcome = 'ATTENDED_COURTESY_PASS'"
        )
    )
    op.drop_constraint(
        "ck_contact_center_appointments_outcome",
        "contact_center_appointments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_contact_center_appointments_outcome",
        "contact_center_appointments",
        "outcome IS NULL OR outcome IN ("
        "'ATTENDED_PURCHASE_REPORTED', "
        "'ATTENDED_NO_PURCHASE', "
        "'NO_SHOW', "
        "'CANCELLED', "
        "'RESCHEDULED'"
        ")",
    )
