from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROUTES = REPOSITORY_ROOT / "frontend/src/app/app.routes.ts"
LAYOUT_TS = REPOSITORY_ROOT / "frontend/src/app/layout/layout.component.ts"
ACCESS_GUARD = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center-access.guard.ts"
)
COMPONENT_TS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center.component.ts"
)
COMPONENT_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center.component.html"
)
COMPONENT_CSS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center.component.css"
)
SERVICE_TS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center.service.ts"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contact_center_route_is_guarded_and_lazy_loaded():
    routes = _read(APP_ROUTES)

    assert "path: 'contact-center'" in routes
    assert "canActivate: [contactCenterAccessGuard]" in routes
    assert "import('./contact-center/contact-center.component')" in routes


def test_contact_center_initial_frontend_access_is_narrow():
    guard = _read(ACCESS_GUARD)

    assert "'ADMICORP'" in guard
    assert "'SANDRA'" in guard
    assert "CONTACT_CENTER_INITIAL_ROLES" in guard
    assert "CONTACT_CENTER_INITIAL_USERS" in guard

    # No abrir el rollout por roles administrativos genéricos.
    assert "'ADMINISTRADOR'" not in guard
    assert "'GERENTE'" not in guard
    assert "'LECTOR_GLOBAL'" not in guard


def test_contact_center_menu_waits_for_backend_access_confirmation():
    layout = _read(LAYOUT_TS)

    assert "habilitarContactCenterEnMenuSiAplica" in layout
    assert "canAccessContactCenter(user)" in layout
    assert "/contact-center/access" in layout
    assert "if (!response?.allowed)" in layout


def test_contact_center_v1_keeps_logic_out_of_inline_templates_and_styles():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)
    component_css = _read(COMPONENT_CSS)

    assert "templateUrl: './contact-center.component.html'" in component_ts
    assert "styleUrls: ['./contact-center.component.css']" in component_ts
    assert "template:" not in component_ts
    assert "styles:" not in component_ts
    assert "<style" not in component_html.lower()
    assert ".cc-page" in component_css


def test_contact_center_v1_exposes_portfolio_crm_and_appointment_calendar():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)
    service = _read(SERVICE_TS)

    assert "type ContactCenterTab = 'PORTFOLIO' | 'CRM' | 'APPOINTMENTS'" in component_ts
    assert "type AppointmentView = 'TABLE' | 'CALENDAR'" in component_ts
    assert "calendarCells" in component_ts

    assert "Mi cartera" in component_html
    assert "CRM / Funnel" in component_html
    assert "Citas" in component_html
    assert "calendar-grid" in component_html

    assert "getContacts(" in service
    assert "getCrmCandidates(" in service
    assert "getAppointments(" in service
    assert "getReport(" in service
