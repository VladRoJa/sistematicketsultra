from __future__ import annotations

from typing import Any

from app.models.sucursal_model import Sucursal


SUCURSAL_AUDIENCE_OPERATIONAL = "operational"
SUCURSAL_AUDIENCE_ANALYTICAL = "analytical"
VALID_SUCURSAL_AUDIENCES = {
    SUCURSAL_AUDIENCE_OPERATIONAL,
    SUCURSAL_AUDIENCE_ANALYTICAL,
}


def normalize_sucursal_audience(
    value: Any,
    *,
    default: str = SUCURSAL_AUDIENCE_OPERATIONAL,
) -> str:
    normalized = str(value or default).strip().lower()
    if normalized not in VALID_SUCURSAL_AUDIENCES:
        raise ValueError(
            f"audience inválida: {normalized!r}. "
            f"Valores válidos: {sorted(VALID_SUCURSAL_AUDIENCES)}"
        )
    return normalized


def apply_sucursal_audience(
    query,
    *,
    audience: str = SUCURSAL_AUDIENCE_OPERATIONAL,
    model=Sucursal,
):
    """Aplica la política canónica de participación de sucursales.

    operational:
        Incluye sucursales demo. Se usa en módulos transaccionales como Tickets,
        Inventario, PM y Maintenance Planner para poder probar el flujo completo.

    analytical:
        Excluye sucursales demo. Se usa en BI, Track, Forecast, Control y
        consolidados ejecutivos para no contaminar indicadores reales.
    """

    normalized = normalize_sucursal_audience(audience)
    if normalized == SUCURSAL_AUDIENCE_ANALYTICAL:
        return query.filter(model.is_demo.is_(False))
    return query


def analytical_sucursal_condition(model=Sucursal):
    """Condición SQLAlchemy reutilizable para joins analíticos."""

    return model.is_demo.is_(False)


def is_demo_sucursal(sucursal: Any) -> bool:
    return bool(getattr(sucursal, "is_demo", False))


def is_analytical_sucursal(sucursal: Any) -> bool:
    return sucursal is not None and not is_demo_sucursal(sucursal)


def parse_include_demo(value: Any, *, default: bool = True) -> bool:
    """Parsea flags HTTP sin aceptar silenciosamente valores ambiguos."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "si", "sí"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError("include_demo debe ser true/false.")
