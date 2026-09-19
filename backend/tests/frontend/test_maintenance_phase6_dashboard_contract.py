from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

DASHBOARD_SERVICE = REPOSITORY_ROOT / (
    "backend/app/services/maintenance_weekly_dashboard_service.py"
)
PREVENTIVE_ROUTES = REPOSITORY_ROOT / (
    "backend/app/routes/maintenance_preventive_routes.py"
)
DASHBOARD_TS = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-weekly-dashboard/"
    "maintenance-weekly-dashboard.component.ts"
)
DASHBOARD_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-weekly-dashboard/"
    "maintenance-weekly-dashboard.component.html"
)
DASHBOARD_CSS = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-weekly-dashboard/"
    "maintenance-weekly-dashboard.component.css"
)
APP_ROUTES = REPOSITORY_ROOT / "frontend/src/app/app.routes.ts"
LAYOUT = REPOSITORY_ROOT / "frontend/src/app/layout/layout.component.ts"
TICKETS_TS = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/"
    "pantalla-ver-tickets.component.ts"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_uses_canonical_weekly_cohorts():
    service = _read(DASHBOARD_SERVICE)

    assert "fecha_programada_original" in service
    assert "fecha_compromiso_original" in service
    assert "fecha_validacion_cierre" in service
    assert "strict_compliance_percent" in service
    assert "current_progress_percent" in service
    assert "fulfillment_percent" in service
    assert "<= _corrective_original_due(ticket)" in service
    assert "_ticket_was_reprogrammed" in service
    assert '"delta": len(backlog_end) - len(backlog_start)' in service
    assert "backlog_overdue_start" in service
    assert "backlog_overdue_end" in service
    assert "_corrective_due_as_of" in service
    assert "demand_reactive" in service
    assert "demand_detected_preventive" in service
    assert "_aging_bucket" in service


def test_preventive_validation_does_not_count_technician_finish_as_manager_validation():
    service = _read(DASHBOARD_SERVICE)

    assert "En preventivos fecha_finalizado es ejecución del técnico" in service
    assert "return _business_date(ticket.fecha_validacion_cierre)" in service


def test_dashboard_exposes_overview_context_and_drilldown_routes():
    routes = _read(PREVENTIVE_ROUTES)

    assert '"/dashboard/context"' in routes
    assert '"/dashboard/weekly"' in routes
    assert '"/dashboard/drilldown"' in routes
    assert "build_weekly_dashboard" in routes
    assert "build_dashboard_drilldown" in routes


def test_dashboard_component_uses_separate_files_and_clickable_metrics():
    ts = _read(DASHBOARD_TS)
    html = _read(DASHBOARD_HTML)

    assert "templateUrl: './maintenance-weekly-dashboard.component.html'" in ts
    assert "styleUrls: ['./maintenance-weekly-dashboard.component.css']" in ts
    assert "template:" not in ts
    assert "styles:" not in ts
    assert DASHBOARD_HTML.exists()
    assert DASHBOARD_CSS.exists()

    assert "openDrilldown" in ts
    assert "preventive.programmed" in html
    assert "preventive.validated_on_time" in html
    assert "corrective.due" in html
    assert "corrective.demand" in html
    assert "backlog.start" in html
    assert "backlog.end" in html
    assert "backlog.overdue_start" in html
    assert "backlog.overdue_end" in html
    assert "corrective.demand_reactive" in html
    assert "corrective.demand_detected_preventive" in html
    assert "1–7 días" in html
    assert "+30 días" in html
    assert "Abrir en Tickets" in html
    assert "Última reprogramación" in html
    assert "ticket.reprogramaciones[0].motivo" in html
    assert "ticket.reprogramaciones[0].fecha_nueva" in html


def test_dashboard_route_and_menu_are_backend_authorized():
    routes = _read(APP_ROUTES)
    layout = _read(LAYOUT)

    assert "path: 'panel-mantenimiento'" in routes
    assert "MaintenanceWeeklyDashboardComponent" in routes
    assert "Panel de mantenimiento" in layout
    assert "/tickets/preventive-planning/dashboard/context" in layout
    assert "El backend es autoridad" in layout


def test_dashboard_ticket_jump_is_resolved_by_tickets_query_param():
    dashboard_ts = _read(DASHBOARD_TS)
    tickets_ts = _read(TICKETS_TS)

    assert "ticket_id: ticket.id" in dashboard_ts
    assert "ticketIdDesdeQueryParam" in tickets_ts
    assert "programarAplicacionFiltroTicketDesdeQueryParam" in tickets_ts
    assert "Number(row.id) === Number(ticketId)" in tickets_ts
    assert "this.filteredTickets = [ticket]" in tickets_ts
