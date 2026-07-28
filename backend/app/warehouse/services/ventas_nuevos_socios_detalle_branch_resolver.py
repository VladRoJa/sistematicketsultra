from __future__ import annotations

from typing import Any

from app.extensions import db
from app.routine_control.pipeline.branch_resolver import (
    resolve_gasca_branch_id,
)


def resolve_ventas_nuevos_socios_detalle_branch_id(
    source_branch_name: object,
    *,
    session: Any | None = None,
) -> int | None:
    """
    Resuelve una sucursal RAW de Gasca hacia sucursal_id.

    Reutiliza el catálogo Track y la source_family
    'gasca_family'. Cuando no se inyecta una sesión,
    utiliza la sesión Flask-SQLAlchemy actual.
    """
    active_session = (
        session
        if session is not None
        else db.session
    )

    return resolve_gasca_branch_id(
        source_branch_name,
        session=active_session,
    )
