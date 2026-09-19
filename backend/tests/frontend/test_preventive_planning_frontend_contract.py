from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

COMPONENT_TS = REPOSITORY_ROOT / (
    "frontend/src/app/tickets-preventive-planning/"
    "tickets-preventive-planning.component.ts"
)
COMPONENT_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/tickets-preventive-planning/"
    "tickets-preventive-planning.component.html"
)
COMPONENT_CSS = REPOSITORY_ROOT / (
    "frontend/src/app/tickets-preventive-planning/"
    "tickets-preventive-planning.component.css"
)
SERVICE_TS = REPOSITORY_ROOT / (
    "frontend/src/app/services/maintenance-preventive.service.ts"
)
APP_ROUTES_TS = REPOSITORY_ROOT / "frontend/src/app/app.routes.ts"
LAYOUT_TS = REPOSITORY_ROOT / "frontend/src/app/layout/layout.component.ts"
BACKEND_ROUTES = REPOSITORY_ROOT / (
    "backend/app/routes/maintenance_preventive_routes.py"
)
APP_FACTORY = REPOSITORY_ROOT / "backend/app/__init__.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_preventive_planning_component_uses_separate_ts_html_css():
    component_ts = _read(COMPONENT_TS)

    assert "templateUrl: './tickets-preventive-planning.component.html'" in component_ts
    assert "styleUrls: ['./tickets-preventive-planning.component.css']" in component_ts
    assert "template:" not in component_ts
    assert "styles:" not in component_ts
    assert COMPONENT_HTML.exists()
    assert COMPONENT_CSS.exists()


def test_preventive_planning_lives_under_tickets_route_and_menu():
    routes = _read(APP_ROUTES_TS)
    layout = _read(LAYOUT_TS)

    assert "path: 'programacion-preventiva'" in routes
    assert (
        "./tickets-preventive-planning/"
        "tickets-preventive-planning.component"
    ) in routes
    assert "Programación preventiva" in layout
    assert "/main/programacion-preventiva" in layout
    assert "puedeConfigurarProgramacionPreventivaPorRol" in layout


def test_frontend_service_uses_canonical_preventive_api():
    service = _read(SERVICE_TS)

    assert "$" + "{environment.apiUrl}/tickets/preventive-planning" in service

    for endpoint in (
        "/context",
        "/equipment",
        "/batches",
        "/imports",
        "/template",
        "/validate",
        "/publish",
    ):
        assert endpoint in service


def test_admin_view_supports_manual_family_selection_and_batch_actions():
    html = _read(COMPONENT_HTML)

    assert "Selección por familia" in html
    assert "familyOptions" in html
    assert "selectedEquipmentCount" in html
    assert "Agregar {{ selectedEquipmentCount }} preventivos" in html
    assert "Validar lote" in html
    assert "Publicar {{ batch.items.length }} preventivos" in html
    assert "Cargar y validar" in html


def test_backend_blueprint_is_registered_inside_tickets_namespace():
    routes = _read(BACKEND_ROUTES)
    app_factory = _read(APP_FACTORY)

    assert '"/batches"' in routes
    assert '"/imports"' in routes
    assert '"/template"' in routes
    assert '"/context"' in routes
    assert '"/equipment"' in routes
    assert '"/batches/<int:batch_id>/publish"' in routes

    assert "maintenance_preventive_bp" in app_factory
    assert "/api/tickets/preventive-planning" in app_factory
