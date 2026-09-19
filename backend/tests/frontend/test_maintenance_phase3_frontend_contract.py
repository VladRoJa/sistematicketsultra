from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

CREW_TS = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-crew-config/"
    "maintenance-crew-config.component.ts"
)
CREW_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-crew-config/"
    "maintenance-crew-config.component.html"
)
CREW_CSS = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-crew-config/"
    "maintenance-crew-config.component.css"
)
PROGRAM_TS = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-my-program/"
    "maintenance-my-program.component.ts"
)
PROGRAM_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-my-program/"
    "maintenance-my-program.component.html"
)
PROGRAM_CSS = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-my-program/"
    "maintenance-my-program.component.css"
)
APP_ROUTES = REPOSITORY_ROOT / "frontend/src/app/app.routes.ts"
LAYOUT = REPOSITORY_ROOT / "frontend/src/app/layout/layout.component.ts"
BACKEND_ROUTES = REPOSITORY_ROOT / (
    "backend/app/routes/maintenance_preventive_routes.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_crew_and_my_program_components_use_separate_files():
    crew_ts = _read(CREW_TS)
    program_ts = _read(PROGRAM_TS)

    assert "templateUrl: './maintenance-crew-config.component.html'" in crew_ts
    assert "styleUrls: ['./maintenance-crew-config.component.css']" in crew_ts
    assert "template:" not in crew_ts
    assert "styles:" not in crew_ts

    assert "templateUrl: './maintenance-my-program.component.html'" in program_ts
    assert "styleUrls: ['./maintenance-my-program.component.css']" in program_ts
    assert "template:" not in program_ts
    assert "styles:" not in program_ts

    assert CREW_HTML.exists()
    assert CREW_CSS.exists()
    assert PROGRAM_HTML.exists()
    assert PROGRAM_CSS.exists()


def test_routes_live_under_tickets_main_area():
    routes = _read(APP_ROUTES)

    assert "path: 'cuadrillas-mantenimiento'" in routes
    assert "path: 'mi-programa'" in routes
    assert "MaintenanceCrewConfigComponent" in routes
    assert "MaintenanceMyProgramComponent" in routes


def test_my_program_menu_is_backend_authorized():
    layout = _read(LAYOUT)

    assert "habilitarMiProgramaEnMenu" in layout
    assert "/tickets/preventive-planning/my-program" in layout
    assert "/main/mi-programa" in layout
    assert "El backend es autoridad" in layout


def test_my_program_view_is_mobile_card_based_not_table_based():
    html = _read(PROGRAM_HTML)
    css = _read(PROGRAM_CSS)

    assert "work-card" in html
    assert "metric-grid" in html
    assert "<table" not in html
    assert "@media (max-width: 360px)" in css
    assert "@media (max-width: 520px)" in css


def test_backend_exposes_personnel_catalog_and_my_program():
    routes = _read(BACKEND_ROUTES)

    for route in (
        '"/crews"',
        '"/personnel"',
        '"/my-program"',
    ):
        assert route in routes
