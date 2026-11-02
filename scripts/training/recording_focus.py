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

# Pausas didácticas fijadas en el motor CAP-V1, sin alterar la aplicación.
LEAD_MS = 900
POST_MS = 700


def prepare_guidance(page, locator) -> None:
    """Mostrar flecha y cursor sobre un objetivo real, sin interactuar con él."""
    locator.wait_for(state="visible", timeout=15000)
    locator.scroll_into_view_if_needed(timeout=15000)
    rect = locator.bounding_box()
    if not rect or rect["width"] <= 0 or rect["height"] <= 0:
        raise RuntimeError("CAP-V1: objetivo de clic fuera de pantalla.")
    x = rect["x"] + rect["width"] / 2
    y = rect["y"] + rect["height"] / 2
    page.mouse.move(x - 28, y - 23, steps=8)
    page.mouse.move(x, y, steps=9)
    accepted = page.evaluate(
        "(r) => window.__capV1FocusRecorder?.preview?.(r) === true",
        rect,
    )
    if not accepted:
        raise RuntimeError("CAP-V1: la guía anterior al clic no está disponible.")


def guided_action(page, locator, action: str = "click", *,
                  lead_ms: int = LEAD_MS, post_ms: int = POST_MS) -> None:
    """Anticipar el clic, ejecutarlo y dar tiempo a observar el resultado.

    Mantener autorización, selectores y reglas de negocio en Playwright/Suite.
    Solo afecta a la puesta en escena de acciones YA permitidas.
    """
    if action not in ("click", "check", "uncheck"):
        raise ValueError("CAP-V1: tipo de interacción visual no soportado.")
    if not 500 <= lead_ms <= 2000 or not 250 <= post_ms <= 1500:
        raise ValueError("CAP-V1: pausas fuera del rango didáctico admitido.")
    prepare_guidance(page, locator)
    page.wait_for_timeout(lead_ms)
    getattr(locator, action)()
    page.wait_for_timeout(post_ms)


def guided_click(page, locator, **kwargs) -> None:
    guided_action(page, locator, "click", **kwargs)
