from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_create_contact_validates_assignee_as_contact_center_operator():
    service = _read(SERVICE)

    assert "has_contact_center_operator_access(assigned_user)" in service
    assert "has_contact_center_access(assigned_user)" not in service
    assert "no tiene acceso operativo a Contact Center" in service
