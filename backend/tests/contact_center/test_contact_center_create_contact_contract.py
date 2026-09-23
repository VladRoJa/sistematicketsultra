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

def test_manager_manual_contact_is_forced_to_self_and_allowed_branch():
    service = _read(SERVICE)
    routes = (REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py").read_text(
        encoding="utf-8"
    )

    assert "forced_assigned_user_id" in service
    assert "allowed_branch_ids: tuple[int, ...] | None = None" in service
    assert "La asignación forzada debe corresponder al usuario actual." in service
    assert "Selecciona una sucursal autorizada." in service
    assert "Sólo puedes crear contactos para tus sucursales autorizadas." in service

    assert "forced_assigned_user_id=(" in routes
    assert "if access.is_manager" in routes
    assert "allowed_branch_ids=(" in routes

