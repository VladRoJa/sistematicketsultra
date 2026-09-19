from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

REPROGRAM_SERVICE = ROOT / (
    "backend/app/services/maintenance_reprogram_service.py"
)
PREVENTIVE_ROUTES = ROOT / (
    "backend/app/routes/maintenance_preventive_routes.py"
)
REPROGRAM_MODEL = ROOT / (
    "backend/app/models/maintenance_preventive.py"
)
REPROGRAM_MIGRATION = ROOT / (
    "backend/migrations/versions/"
    "e5a9c3d7f1b2_create_maintenance_reprogram_reasons.py"
)
MAINTENANCE_API = ROOT / (
    "frontend/src/app/services/maintenance-preventive.service.ts"
)
CONFIG_TS = ROOT / (
    "frontend/src/app/maintenance-checklist-config/"
    "maintenance-checklist-config.component.ts"
)
CONFIG_HTML = ROOT / (
    "frontend/src/app/maintenance-checklist-config/"
    "maintenance-checklist-config.component.html"
)
DASHBOARD_TS = ROOT / (
    "frontend/src/app/maintenance-weekly-dashboard/"
    "maintenance-weekly-dashboard.component.ts"
)
DASHBOARD_HTML = ROOT / (
    "frontend/src/app/maintenance-weekly-dashboard/"
    "maintenance-weekly-dashboard.component.html"
)
TICKETS_TS = ROOT / (
    "frontend/src/app/pantalla-ver-tickets/"
    "pantalla-ver-tickets.component.ts"
)
TICKETS_HTML = ROOT / (
    "frontend/src/app/pantalla-ver-tickets/"
    "pantalla-ver-tickets.component.html"
)
VALIDATION_DIALOG_HTML = ROOT / (
    "frontend/src/app/pantalla-ver-tickets/modals/"
    "preventive-validation-dialog.component.html"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reprogram_reason_catalog_is_persisted_and_seeded():
    model = _read(REPROGRAM_MODEL)
    migration = _read(REPROGRAM_MIGRATION)

    assert 'class MaintenanceReprogramReasonORM' in model
    assert '"maintenance_reprogram_reasons"' in model
    assert "requiere_comentario" in model
    assert "REFACCION_PENDIENTE" in migration
    assert "PROVEEDOR_EXTERNO" in migration
    assert "EQUIPO_NO_DISPONIBLE" in migration
    assert "REPROGRAMACION_OPERATIVA" in migration
    assert "FALTA_TECNICO" in migration
    assert '"OTRO"' in migration


def test_reprogram_endpoint_is_audited_and_unified():
    service = _read(REPROGRAM_SERVICE)
    routes = _read(PREVENTIVE_ROUTES)

    assert "def reprogramar_ticket_mantenimiento" in service
    assert 'maintenance_type not in {"PREVENTIVO", "CORRECTIVO"}' in service
    assert '"evento": "reprogramacion_mantenimiento"' in service
    assert '"fecha_anterior"' in service
    assert '"fecha_nueva"' in service
    assert '"motivo_key"' in service
    assert '"cambiadoPor"' in service
    assert '"/tickets/<int:ticket_id>/reprogram"' in routes


def test_reprogram_catalog_is_editable_from_existing_preventive_config():
    api = _read(MAINTENANCE_API)
    ts = _read(CONFIG_TS)
    html = _read(CONFIG_HTML)

    assert "getReprogramReasons" in api
    assert "createReprogramReason" in api
    assert "updateReprogramReason" in api
    assert "reprogramMaintenanceTicket" in api
    assert "loadReprogramReasons" in ts
    assert "saveReprogramReason" in ts
    assert "Motivos configurables" in html
    assert "Requiere comentario" in html


def test_dashboard_only_exposes_reprogram_when_backend_catalog_is_available():
    ts = _read(DASHBOARD_TS)
    html = _read(DASHBOARD_HTML)

    assert "reprogramReasons.length > 0" in ts
    assert "canReprogram(ticket)" in html
    assert "Guardar reprogramación" in html
    assert "selectedReprogramReason" in ts


def test_preventive_corrective_relation_is_navigable_in_both_directions():
    dashboard = _read(DASHBOARD_HTML)
    tickets_ts = _read(TICKETS_TS)
    tickets_html = _read(TICKETS_HTML)
    validation = _read(VALIDATION_DIALOG_HTML)

    assert "Ver preventivo #" in dashboard
    assert "ticket.ticket_preventivo_origen_id" in dashboard
    assert "abrirTicketPreventivoOrigen" in tickets_ts
    assert "ticket.ticket_preventivo_origen_id" in tickets_html
    assert "Abrir ticket" in validation
