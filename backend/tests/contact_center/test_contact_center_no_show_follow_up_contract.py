from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROUTES = REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py"
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_show_case_returns_to_shared_follow_up_without_reassignment():
    service = _read(SERVICE)
    routes = _read(ROUTES)

    assert "def is_no_show_follow_up_case(" in service
    assert 'case.status != "IN_PROGRESS"' in service
    assert 'ContactCenterAppointmentORM.status == "CLOSED"' in service
    assert 'ContactCenterAppointmentORM.outcome == "NO_SHOW"' in service

    assert "allow_foreign_case: bool = False" in service
    assert "and not allow_foreign_case" in service

    assert "allow_no_show_follow_up: bool = False" in routes
    assert "allow_no_show_follow_up and is_no_show_follow_up_case(case)" in routes
    assert "allow_foreign_case=allow_foreign_case" in routes


def test_manager_portfolio_and_detail_include_recoverable_no_show_case():
    service = _read(SERVICE)
    routes = _read(ROUTES)

    assert "no_show_follow_up_exists" in service
    assert 'ContactCenterCaseORM.status == "IN_PROGRESS"' in service
    assert "ContactCenterAppointmentORM.outcome == "NO_SHOW"" in service

    assert "def _detail_case_is_no_show_follow_up(" in routes
    assert "or _detail_case_is_no_show_follow_up(detail, case)" in routes
