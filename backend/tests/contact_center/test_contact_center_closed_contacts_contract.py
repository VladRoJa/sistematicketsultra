from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"
ROUTES = REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contact_list_keeps_closed_contacts_visible_by_default():
    service = _read(SERVICE)

    assert "cases_query = ContactCenterCaseORM.query" in service
    assert '.filter(ContactCenterCaseORM.status != "CLOSED")' not in service
    assert "seen_contact_ids: set[int] = set()" in service
    assert "if contact_id in seen_contact_ids:" in service


def test_contact_list_prefers_active_case_when_contact_has_history():
    service = _read(SERVICE)

    assert "sql_case(" in service
    assert '(ContactCenterCaseORM.status == "CLOSED", 1)' in service


def test_report_active_case_kpi_still_excludes_closed_contacts():
    routes = _read(ROUTES)

    assert "active_contacts = [" in routes
    assert '!= "CLOSED"' in routes
    assert '"active_cases": len(active_contacts)' in routes
