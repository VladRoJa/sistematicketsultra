from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODAL_TS = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/modals/"
    "asignar-fecha-modal.component.ts"
)
MODAL_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/modals/"
    "asignar-fecha-modal.component.html"
)
PARENT_TS = REPOSITORY_ROOT / (
    "frontend/src/app/pantalla-ver-tickets/"
    "pantalla-ver-tickets.component.ts"
)
TYPES_TS = REPOSITORY_ROOT / "frontend/src/app/types/ticket.ts"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_modal_muestra_familia_del_inventario_como_readonly_y_carga_sus_fallas():
    modal_ts = _read(MODAL_TS)
    modal_html = _read(MODAL_HTML)

    assert "value.inventario?.familia_equipo_id ?? null" in modal_ts
    assert "value.inventario?.familia_equipo?.nombre || ''" in modal_ts
    assert "this.cargarFallas(this.familiaEquipoId)" in modal_ts
    assert "obtenerFallas(familiaEquipoId)" in modal_ts
    assert "Familia del equipo" in modal_html
    assert "{{ familiaEquipoNombre }}" in modal_html
    assert "(ngModelChange)=\"cambiarFamilia($event)\"" not in modal_html


def test_modal_bloquea_aparato_sin_familia_y_no_envia_familia():
    modal_ts = _read(MODAL_TS)
    modal_html = _read(MODAL_HTML)
    parent_ts = _read(PARENT_TS)
    types_ts = _read(TYPES_TS)

    warning = (
        "Este aparato no tiene una familia asignada. "
        "Clasifícalo primero desde Inventario."
    )
    assert warning in modal_ts
    assert warning in modal_html
    assert '[disabled]="guardarDeshabilitado"' in modal_html
    assert "payload.familia_equipo_id" not in modal_ts
    assert "familia_equipo_id: event.familia_equipo_id" not in parent_ts

    payload_contract = types_ts.split(
        "export interface CompromisoMantenimientoPayload",
        1,
    )[1].split("}", 1)[0]
    assert "familia_equipo_id" not in payload_contract
