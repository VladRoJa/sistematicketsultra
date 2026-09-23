from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROUTES = REPOSITORY_ROOT / "backend/app/routes/contact_center_routes.py"
SERVICE = REPOSITORY_ROOT / "backend/app/services/contact_center_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_crm_import_accepts_confirmed_display_name():
    routes = _read(ROUTES)
    service = _read(SERVICE)

    assert 'display_name=payload.get("display_name")' in routes
    assert "display_name: str | None = None" in service
    assert "confirmed_display_name = _clean_text(display_name)" in service
    assert "display_name=confirmed_display_name or _clean_text(source.name)" in service


def test_crm_import_display_name_is_bounded_to_contact_column():
    service = _read(SERVICE)

    assert "len(confirmed_display_name) > 255" in service
    assert "no puede superar 255 caracteres" in service
