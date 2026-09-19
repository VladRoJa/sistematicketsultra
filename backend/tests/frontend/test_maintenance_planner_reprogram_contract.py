from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

PLANNER_SERVICE = ROOT / (
    "frontend/src/app/maintenance-planner/"
    "maintenance-planner.service.ts"
)
PLANNER_COMPONENT = ROOT / (
    "frontend/src/app/maintenance-planner/"
    "maintenance-planner.component.ts"
)
PLANNER_DIALOG = ROOT / (
    "frontend/src/app/maintenance-planner/"
    "maintenance-planner-ticket-dialog.component.ts"
)
REPROGRAM_DIALOG_TS = ROOT / (
    "frontend/src/app/maintenance-planner/"
    "maintenance-reprogram-dialog.component.ts"
)
REPROGRAM_DIALOG_HTML = ROOT / (
    "frontend/src/app/maintenance-planner/"
    "maintenance-reprogram-dialog.component.html"
)
REPROGRAM_DIALOG_CSS = ROOT / (
    "frontend/src/app/maintenance-planner/"
    "maintenance-reprogram-dialog.component.css"
)
TICKETS_TS = ROOT / (
    "frontend/src/app/pantalla-ver-tickets/"
    "pantalla-ver-tickets.component.ts"
)
PLANNER_BACKEND = ROOT / (
    "backend/app/maintenance_planner/service.py"
)
TICKET_ROUTES = ROOT / "backend/app/routes/ticket_routes.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reprogram_dialog_is_catalog_backed_and_separate_files():
    ts = _read(REPROGRAM_DIALOG_TS)
    html = _read(REPROGRAM_DIALOG_HTML)

    assert "MaintenancePreventiveService" in ts
    assert "getReprogramReasons()" in ts
    assert "reasonId" in ts
    assert "requiere_comentario" in ts
    assert "templateUrl: './maintenance-reprogram-dialog.component.html'" in ts
    assert "styleUrls: ['./maintenance-reprogram-dialog.component.css']" in ts
    assert REPROGRAM_DIALOG_HTML.exists()
    assert REPROGRAM_DIALOG_CSS.exists()
    assert "Guardar reprogramación" in html


def test_planner_reprogramming_uses_canonical_endpoint_not_schedule_endpoint():
    service = _read(PLANNER_SERVICE)

    assert "can_reprogram: boolean" in service
    assert "reprogramMaintenanceTicket" in service
    assert "reason_id: reasonId" in service

    reprogram_section = service.split(
        "/** Reprogramación auditada:",
        1,
    )[1].split(
        "/** Solicitud de cierre",
        1,
    )[0]

    assert "scheduleTicket(" not in reprogram_section
    assert "maintenancePreventiveService" in reprogram_section


def test_planner_drag_and_ticket_dialog_use_catalog_reprogram_dialog():
    component = _read(PLANNER_COMPONENT)
    dialog = _read(PLANNER_DIALOG)

    assert "MaintenanceReprogramDialogComponent" in component
    assert "MaintenanceReprogramDialogComponent" in dialog
    assert "EditarFechaSolucionModalComponent" not in component
    assert "EditarFechaSolucionModalComponent" not in dialog
    assert "permissions.can_reprogram" in component
    assert "readonly canReprogram = this.data.canReprogram" in dialog


def test_backend_planner_is_corrective_only_and_schedule_is_initial_only():
    backend = _read(PLANNER_BACKEND)

    assert 'Ticket.tipo_mantenimiento == "CORRECTIVO"' in backend
    assert "El ticket ya tiene compromiso. Usa la reprogramación" in backend
    assert '"can_reprogram": can_pm_configure(user)' in backend


def test_generic_ticket_commitment_changes_are_guarded():
    routes = _read(TICKET_ROUTES)

    assert "def _maintenance_commitment_change_error" in routes
    assert routes.count(
        "_maintenance_commitment_change_error("
    ) >= 3
    assert "reprogramación auditada de Mantenimiento" in routes


def test_general_tickets_uses_catalog_dialog_for_maintenance_reprogramming():
    ts = _read(TICKETS_TS)

    assert "MaintenanceReprogramDialogComponent" in ts
    assert "reprogramMaintenanceTicket(ticket.id" in ts
    assert "puedeEditarFechaSolucion(ticket" in ts
    assert "'SR_MANTENIMIENTO'" in ts
