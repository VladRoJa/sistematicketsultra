from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

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
SERVICE_TS = REPOSITORY_ROOT / (
    "frontend/src/app/services/maintenance-preventive.service.ts"
)
EXECUTION_SERVICE = REPOSITORY_ROOT / (
    "backend/app/services/maintenance_execution_service.py"
)
PREVENTIVE_ROUTES = REPOSITORY_ROOT / (
    "backend/app/routes/maintenance_preventive_routes.py"
)
BITACORA_MODEL = REPOSITORY_ROOT / "backend/app/models/pm_bitacora.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mobile_execution_keeps_logic_in_ts_and_uses_separate_files():
    ts = _read(PROGRAM_TS)

    assert "FormsModule" in ts
    assert "saveBitacora()" in ts
    assert "uploadEvidence()" in ts
    assert "completeWork()" in ts
    assert "canSaveBitacora" in ts
    assert "canUploadEvidence" in ts
    assert "canCompleteWork" in ts
    assert "template:" not in ts
    assert "styles:" not in ts


def test_mobile_execution_has_guided_three_step_flow():
    html = _read(PROGRAM_HTML)
    css = _read(PROGRAM_CSS)

    assert "Bitácora preventiva" in html
    assert "Foto del trabajo" in html
    assert "Marcar realizado" in html
    assert "Generar ticket correctivo relacionado" in html
    assert "capture=\"environment\"" in html
    assert "check-options" in html
    assert "execution-progress" in css
    assert "execution-button--complete" in css
    assert "@media (max-width: 360px)" in css


def test_frontend_service_exposes_execution_actions():
    service = _read(SERVICE_TS)

    for fragment in (
        "/bitacora",
        "/evidence",
        "/complete",
        "getWorkDetail",
        "createWorkBitacora",
        "uploadWorkEvidence",
        "completeWork",
    ):
        assert fragment in service


def test_backend_requires_ticket_owned_bitacora_and_evidence():
    service = _read(EXECUTION_SERVICE)

    assert "func.lower(Ticket.asignado_a) == username.casefold()" in service
    assert "Debes guardar una bitácora antes de marcar realizado." in service
    assert "Debes adjuntar evidencia antes de marcar realizado." in service
    assert "DETECTADO_EN_PREVENTIVO" in service
    assert "ticket_preventivo_origen_id=preventive.id" in service


def test_ticket_linked_bitacora_preserves_legacy_nullable_contract():
    model = _read(BITACORA_MODEL)

    assert 'db.ForeignKey("tickets.id", ondelete="SET NULL")' in model
    assert "nullable=True" in model
    assert "estado_encontrado" in model
    assert "hallazgo_detectado" in model
    assert "hallazgo_descripcion" in model


def test_execution_routes_are_separate_retryable_steps():
    routes = _read(PREVENTIVE_ROUTES)

    for fragment in (
        '"/my-program/<int:ticket_id>"',
        '"/my-program/<int:ticket_id>/bitacora"',
        '"/my-program/<int:ticket_id>/evidence"',
        '"/my-program/<int:ticket_id>/complete"',
    ):
        assert fragment in routes
