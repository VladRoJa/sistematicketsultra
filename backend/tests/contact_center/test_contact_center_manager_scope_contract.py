from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROUTES = REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py"
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_manager_appointments_are_scoped_by_allowed_branch_ids():
    routes = _read(ROUTES)
    service = _read(SERVICE)

    assert "access.allowed_branch_ids" in routes
    assert "if access.is_manager" in routes
    assert "ContactCenterAppointmentORM.sucursal_id.in_(allowed_branch_ids)" in service


def test_manager_is_blocked_from_contact_center_operator_endpoints():
    routes = _read(ROUTES)

    assert "def _assert_operator_access(access)" in routes
    assert "El acceso de gerente está limitado a citas de su sucursal." in routes
    assert "def get_contacts():" in routes
    assert "def get_crm_candidates():" in routes
    assert "def post_interaction(case_id: int):" in routes


def test_manager_cannot_reschedule_appointments():
    routes = _read(ROUTES)

    assert "def post_reschedule_appointment(appointment_id: int):" in routes
    assert "Los gerentes sólo pueden registrar el resultado de la cita." in routes
