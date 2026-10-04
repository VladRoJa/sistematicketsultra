"""Proyección conservadora de costos persistidos para Campaign V2 Reporting."""

from __future__ import annotations

from typing import Any, Mapping


def extract_campaign_cost_projection(
    analytics_json: Any,
) -> dict[str, Any]:
    """Proyecta sólo costos físicamente soportados por evidencia persistida.

    M27 no tiene un shape real de costo más allá de analytics.cost ausente
    o vacío, por lo que ambos estados permanecen explícitamente unavailable.
    """
    if not isinstance(analytics_json, Mapping):
        return _unavailable_cost()

    cost = analytics_json.get("cost")
    if not isinstance(cost, Mapping) or not cost:
        return _unavailable_cost()

    # Deliberadamente no se interpretan campos de costo todavía. Extender
    # esta frontera requiere payload real sanitizado + fixture + test.
    return _unavailable_cost()


def _unavailable_cost() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "currency": None,
        "total": None,
    }
