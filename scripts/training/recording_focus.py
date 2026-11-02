"""Foco visual para grabaciones Playwright, nunca para la interfaz Angular.

El overlay es pasivo (pointer-events:none) y no abre requests ni toca estados.
Se instala en contextos YA permitidos por los gates existentes.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCRIPT = BASE / "recording_focus.js"
STYLE = BASE / "recording_focus.css"


def install_focus_context(context) -> None:
    """Registrar el cursor al crear cada documento (incluye cambio de cuenta)."""
    context.add_init_script(path=str(SCRIPT))


def install_focus_page(page) -> None:
    """Aplicar solo CSS de captura después de cada navegación real."""
    page.add_style_tag(path=str(STYLE))
    if not page.evaluate(
        "() => !!window.__capV1FocusRecorder?.ready?.()"
    ):
        raise RuntimeError("CAP-V1: overlay de clics no instalado en la grabación.")
