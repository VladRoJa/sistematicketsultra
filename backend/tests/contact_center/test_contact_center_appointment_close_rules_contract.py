from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_appointment_result_rules_close_case_except_no_show():
    service = _read(SERVICE)

    assert "def _apply_appointment_result(" in service
    assert 'if outcome == "NO_SHOW":' in service
    assert 'case.status = "IN_PROGRESS"' in service
    assert "case.closed_at = None" in service
    assert "case.closed_by_user_id = None" in service

    assert 'else:\n        case.status = "CLOSED"' in service
    assert "case.closed_at = changed_at" in service
    assert "case.closed_by_user_id = changed_by_user_id" in service


def test_purchase_result_keeps_purchase_verification_flow():
    service = _read(SERVICE)

    assert 'if outcome == "ATTENDED_PURCHASE_REPORTED":' in service
    assert "appointment.purchase_reported = True" in service
    assert 'appointment.purchase_verification_status = "REPORTED_PENDING"' in service
    assert "def _clear_appointment_purchase_state(" in service
