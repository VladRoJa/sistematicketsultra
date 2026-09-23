from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROUTES = REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py"
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_manager_portfolio_is_own_cases_inside_allowed_branches():
    routes = _read(ROUTES)
    service = _read(SERVICE)

    assert "include_all_assignees=not access.is_manager" in routes
    assert "allowed_branch_ids=(" in routes
    assert "if not is_supervisor and not include_all_assignees:" in service
    assert "ContactCenterCaseORM.assigned_user_id == actor.id" in service
    assert "ContactCenterCaseORM.sucursal_id.in_(allowed_branch_ids)" in service


def test_manager_can_write_only_own_case_and_authorized_appointment_branch():
    routes = _read(ROUTES)

    assert "def _assert_case_access(case: ContactCenterCaseORM, actor, access)" in routes
    assert "El caso no pertenece a tu cartera." in routes
    assert "El caso no pertenece a una sucursal autorizada." in routes
    assert "def post_interaction(case_id: int):" in routes
    assert "def post_appointment(case_id: int):" in routes
    assert "Sólo puedes agendar citas en tus sucursales autorizadas." in routes


def test_manager_crm_is_scoped_to_allowed_branches():
    routes = _read(ROUTES)
    service = _read(SERVICE)

    assert "branch_scope = (" in routes
    assert "allowed_branch_ids=branch_scope" in routes
    assert "MarketingIventasContactORM.sucursal_id.in_(allowed_branch_ids)" in service
    assert "El lead CRM no pertenece a una sucursal autorizada." in service


def test_manager_cannot_reschedule_appointments():
    routes = _read(ROUTES)

    assert "def post_reschedule_appointment(appointment_id: int):" in routes
    assert "Los gerentes sólo pueden registrar el resultado de la cita." in routes


def test_manager_self_scheduled_appointment_skips_email_notification():
    routes = _read(ROUTES)

    assert '"SKIPPED_SELF_SCHEDULED" if access.is_manager else "FAILED"' in routes
    assert "if not access.is_manager:" in routes

def test_manager_contact_detail_is_scoped_to_own_cases_and_links():
    routes = _read(ROUTES)

    assert "def _scope_contact_detail_for_manager(detail, actor, access):" in routes
    assert 'detail["cases"] = cases' in routes
    assert 'detail["interactions"] = [' in routes
    assert 'detail["appointments"] = [' in routes
    assert 'detail["links"] = [' in routes
    assert "allowed_source_refs" in routes


def test_manager_manual_create_is_restricted_but_admin_actions_stay_blocked():
    routes = _read(ROUTES)

    assert "def post_contact():" in routes
    assert "forced_assigned_user_id=(" in routes
    assert "access.allowed_branch_ids" in routes

    assert "Esta acción está reservada para operadores de Contact Center." in routes
    assert "def get_duplicates():" in routes
    assert "def post_merge_contacts():" in routes
    assert "def post_assign_case(case_id: int):" in routes
    assert "def post_verify_purchase(appointment_id: int):" in routes
