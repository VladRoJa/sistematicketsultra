from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_create_appointment_rejects_second_scheduled_appointment():
    service = _read(SERVICE)

    assert ".with_for_update()" in service
    assert 'ContactCenterAppointmentORM.status == "SCHEDULED"' in service
    assert "Este caso ya tiene una cita programada." in service
    assert "Usa Reagendar para cambiar la fecha o sucursal." in service
