from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROUTES = REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py"
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sandra_and_candy_read_shared_portfolio_and_appointments():
    routes = _read(ROUTES)
    service = _read(SERVICE)

    assert "include_all_assignees=not access.is_manager" in routes
    assert "include_all_assignees: bool = False" in service
    assert "elif not is_supervisor and not include_all_assignees:" in service


def test_shared_read_does_not_grant_shared_case_write():
    routes = _read(ROUTES)
    service = _read(SERVICE)

    assert "if access.is_supervisor or not access.is_manager:" in routes
    assert "int(case.assigned_user_id or 0) != int(actor.id)" in routes
    assert "case.assigned_user_id != actor.id" in service


def test_crm_rows_expose_active_case_owner_for_safe_actions():
    service = _read(SERVICE)

    assert "active_case_owner_ids" in service
    assert '"active_case_assigned_user_id": (' in service
