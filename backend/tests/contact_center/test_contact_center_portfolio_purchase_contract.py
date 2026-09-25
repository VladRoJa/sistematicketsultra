from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_portfolio_exposes_purchase_summary_without_changing_case_status():
    service = _read(SERVICE)

    assert "def _portfolio_purchase_summaries(" in service
    assert "ContactCenterAppointmentORM.purchase_reported.is_(True)" in service
    assert '== "VERIFIED"' in service
    assert "purchase_summaries = _portfolio_purchase_summaries(" in service
    assert 'payload["purchase_summary"] = purchase_summaries.get(contact_id)' in service
    assert 'payload["case"] = serialize_case(case_row)' in service
