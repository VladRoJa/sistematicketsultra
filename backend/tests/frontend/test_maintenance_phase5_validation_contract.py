from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

TICKETS_TS = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/"
    "pantalla-ver-tickets.component.ts"
)
TICKETS_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/"
    "pantalla-ver-tickets.component.html"
)
TICKET_SERVICE = REPOSITORY_ROOT / (
    "frontend/src/app/services/ticket.service.ts"
)
DIALOG_TS = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/modals/"
    "preventive-validation-dialog.component.ts"
)
DIALOG_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/modals/"
    "preventive-validation-dialog.component.html"
)
DIALOG_CSS = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/modals/"
    "preventive-validation-dialog.component.css"
)
TICKET_ROUTES = REPOSITORY_ROOT / (
    "backend/app/routes/ticket_routes.py"
)
TICKET_MODEL = REPOSITORY_ROOT / (
    "backend/app/models/ticket_model.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_preventive_validation_dialog_uses_separate_files():
    ts = _read(DIALOG_TS)

    assert "templateUrl: './preventive-validation-dialog.component.html'" in ts
    assert "styleUrls: ['./preventive-validation-dialog.component.css']" in ts
    assert "template:" not in ts
    assert "styles:" not in ts
    assert DIALOG_HTML.exists()
    assert DIALOG_CSS.exists()


def test_tickets_requires_review_for_preventive_validation():
    ts = _read(TICKETS_TS)
    html = _read(TICKETS_HTML)

    assert "esPreventivo(ticket)" in ts
    assert "abrirRevisionPreventivo(ticket)" in ts
    assert "!this.esPreventivo(ticket)" in ts
    assert "Revisar preventivo" in html
    assert "fact_check" in html
    assert "*ngIf=\"esPreventivo(ticket); else validacionCorrectiva\"" in html


def test_preventive_review_contains_operational_evidence():
    html = _read(DIALOG_HTML)

    assert "Última ejecución" in html
    assert "Estado encontrado" in html
    assert "Trabajo realizado" in html
    assert "Checklist" in html
    assert "Hallazgo detectado" in html
    assert "Correctivos generados" in html
    assert "Ver evidencia" in html
    assert "Aceptar preventivo" in html
    assert "Confirmar rechazo" in html


def test_ticket_service_exposes_validation_detail_endpoint():
    service = _read(TICKET_SERVICE)

    assert "getPreventiveValidationDetail" in service
    assert "/cierre/preventivo-detalle/" in service


def test_backend_detail_uses_real_validation_permission_and_requirements():
    routes = _read(TICKET_ROUTES)

    assert "def cierre_preventivo_detalle" in routes
    assert "_puede_validar_cierre_gerente(user, ticket)" in routes
    assert "_preventive_close_requirement_error(t)" in routes
    assert "PmBitacoraORM.ticket_id == ticket.id" in routes
    assert "TicketAttachmentORM.deleted_at.is_(None)" in routes
    assert "ticket_preventivo_origen_id == ticket.id" in routes


def test_manager_rejection_does_not_expose_preventive_scheduling():
    routes = _read(TICKET_ROUTES)
    dialog_ts = _read(DIALOG_TS)
    dialog_html = _read(DIALOG_HTML)

    assert "El gerente puede rechazar el preventivo" in routes
    assert "no reprogramarlo desde la validación" in routes
    assert "newProgramDate" not in dialog_ts
    assert "Nueva fecha programada" not in dialog_html
    assert "nueva_fecha_solucion" not in dialog_ts
