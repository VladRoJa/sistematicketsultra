from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"
ROUTES = REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py"
MODEL = REPOSITORY_ROOT / "backend/app/models/contact_center.py"
MIGRATION = REPOSITORY_ROOT / (
    "backend/migrations/versions/"
    "cca2b3c4d5e6_add_contact_center_appointment_result_events.py"
)
VENTA_REPOSITORY = REPOSITORY_ROOT / (
    "backend/app/warehouse/services/venta_total_repository.py"
)
TRACK_PIPELINE = REPOSITORY_ROOT / (
    "backend/app/warehouse/services/track_daily_pipeline_service.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_result_corrections_are_audited_append_only():
    model = _read(MODEL)
    migration = _read(MIGRATION)
    service = _read(SERVICE)

    assert "class ContactCenterAppointmentResultEventORM" in model
    assert 'source IN (\'MANUAL_CORRECTION\', \'VENTA_TOTAL_AUTO\')' in migration
    assert "def _record_appointment_result_event(" in service
    assert 'source="MANUAL_CORRECTION"' in service
    assert 'source="VENTA_TOTAL_AUTO"' in service


def test_closed_appointment_can_be_corrected_but_verified_purchase_cannot_be_downgraded():
    service = _read(SERVICE)
    routes = _read(ROUTES)

    assert "def correct_appointment_result(" in service
    assert 'appointment.status not in {"CLOSED", "CANCELLED"}' in service
    assert 'appointment.purchase_verification_status == "VERIFIED"' in service
    assert "La cita ya tiene una compra validada por Venta Total." in service

    assert '"/appointments/<int:appointment_id>/correct-result"' in routes
    assert "_assert_appointment_access(appointment, actor, access)" in routes
    assert "verify_appointment_purchase(appointment.id)" in routes


def test_venta_total_match_requires_membership_valid_status_and_purchase_after_appointment_time():
    service = _read(SERVICE)

    assert "def _is_membership_purchase_row(" in service
    assert 'product_key == "MEMBRESIA"' in service
    assert '"MEMBRESIA" in sale_type' in service
    assert "MEMBERSHIP_PURCHASE_TERMS" in service
    assert "if not _is_membership_purchase_row(row):" in service

    assert "_is_valid_status(row.estatus)" in service
    assert "_parse_venta_total_row_local_datetime(row)" in service
    assert "if transaction_local < scheduled_local:" in service
    assert '"%H:%M:%S"' in service
    assert '"%H:%M"' in service


def test_automatic_reconciliation_is_conservative():
    service = _read(SERVICE)

    assert "def reconcile_contact_center_appointments_from_venta_total(" in service
    assert 'ContactCenterAppointmentORM.status == "SCHEDULED"' in service
    assert '("NO_SHOW", "ATTENDED_NO_PURCHASE")' in service
    assert '== "ATTENDED_PURCHASE_REPORTED"' in service
    assert "ContactCenterAppointmentORM.purchase_verification_status" in service
    assert '!= "VERIFIED"' in service
    assert 'ContactCenterAppointmentORM.status == "CANCELLED"' not in service
    assert 'ContactCenterAppointmentORM.status == "RESCHEDULED"' not in service
    assert ".order_by(ContactCenterAppointmentORM.scheduled_at.desc())" in service


def test_reported_purchase_can_be_auto_verified_without_fake_result_correction():
    service = _read(SERVICE)

    assert 'if appointment.outcome == "ATTENDED_PURCHASE_REPORTED":' in service
    assert "_apply_verified_purchase_match(appointment, match)" in service
    assert 'source="VENTA_TOTAL_AUTO"' in service


def test_one_venta_total_transaction_cannot_close_multiple_appointments():
    service = _read(SERVICE)

    assert "used_transactions: set[tuple[int, str]] = set()" in service
    assert "transaction_identity in used_transactions" in service
    assert "used_transactions.add(transaction_identity)" in service
    assert "already_claimed" in service
    assert "venta_total_snapshot_row_id" in service


def test_canonical_venta_total_hooks_are_best_effort_after_commit():
    venta_repository = _read(VENTA_REPOSITORY)
    track_pipeline = _read(TRACK_PIPELINE)

    assert "def _reconcile_contact_center_purchases_best_effort(" in venta_repository
    assert "Contact Center purchase reconciliation failed" in venta_repository
    assert "db.session.commit()" in venta_repository

    assert "def _reconcile_contact_center_purchases_best_effort(" in track_pipeline
    assert "Contact Center purchase reconciliation failed" in track_pipeline
    assert "db.session.commit()" in track_pipeline