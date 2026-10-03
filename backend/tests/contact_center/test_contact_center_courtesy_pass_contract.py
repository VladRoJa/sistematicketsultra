from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE = REPO_ROOT / "backend/app/services/contact_center_service.py"
MODEL = REPO_ROOT / "backend/app/models/contact_center.py"
MIGRATION = (
    REPO_ROOT
    / "backend/migrations/versions/c3f7a1d9b2e6_add_contact_center_courtesy_pass_outcome.py"
)
MODELS_TS = REPO_ROOT / "frontend/src/app/contact-center/contact-center.models.ts"
APPOINTMENT_DIALOG_TS = (
    REPO_ROOT
    / "frontend/src/app/contact-center/contact-center-appointment-dialog.component.ts"
)
COMPONENT_TS = REPO_ROOT / "frontend/src/app/contact-center/contact-center.component.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_courtesy_pass_is_a_first_class_appointment_outcome():
    service = _read(SERVICE)
    model = _read(MODEL)
    migration = _read(MIGRATION)
    models_ts = _read(MODELS_TS)
    dialog = _read(APPOINTMENT_DIALOG_TS)
    component = _read(COMPONENT_TS)

    assert '"ATTENDED_COURTESY_PASS"' in service
    assert "'ATTENDED_COURTESY_PASS'" in model
    assert "'ATTENDED_COURTESY_PASS'" in migration
    assert "'ATTENDED_COURTESY_PASS'" in models_ts
    assert "Visitó y activó pase de cortesía/recorrido" in dialog
    assert "Visitó y activó pase de cortesía/recorrido" in component


def test_courtesy_pass_remains_open_and_eligible_for_later_paid_purchase_reconciliation():
    service = _read(SERVICE)

    assert 'if outcome in {"NO_SHOW", "ATTENDED_COURTESY_PASS"}:' in service
    assert '"NO_SHOW",' in service
    assert '"ATTENDED_NO_PURCHASE",' in service
    assert '"ATTENDED_COURTESY_PASS",' in service


def test_venta_total_requires_positive_amount_before_verifying_purchase():
    service = _read(SERVICE)
    migration = _read(MIGRATION)

    assert 'paid_grouped = {' in service
    assert ') > Decimal("0")' in service
    assert 'COALESCE(appointment.verified_amount, 0) <= 0' in migration
    assert "'ATTENDED_COURTESY_PASS'" in migration
    assert "status = 'IN_PROGRESS'" in migration
