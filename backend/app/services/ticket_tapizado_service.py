"""Creación atómica de vínculos multiaparato en tickets de tapizado.

El selector Angular se habilitará en M3. No agrega endpoints ni amplía permisos.
"""

from datetime import datetime, timezone

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models.ticket_aparato import TicketAparatoORM


MAX_APARATOS_TAPIZADO = 50
TIPO_TRABAJO_TAPIZADO = "TAPIZADO"


def normalizar_payload_tapizado(data):
    """Devuelve (tipo_trabajo, aparato_ids) o (None, None) para V1.

    No transforma peticiones inválidas de multiselección en tickets simples.
    """
    tipo = data.get("tipo_trabajo")
    ids_presentes = "aparatos_ids" in data

    if tipo is None and not ids_presentes:
        return None, None

    if tipo != TIPO_TRABAJO_TAPIZADO:
        raise ValueError(
            "aparatos_ids requiere tipo_trabajo=TAPIZADO; "
            "solo TAPIZADO está habilitado."
        )

    raw = data.get("aparatos_ids")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_APARATOS_TAPIZADO:
        raise ValueError(
            "Tapizado requiere entre 1 y 50 aparatos del inventario."
        )

    ids = []
    vistos = set()
    for value in raw:
        if isinstance(value, bool) or (
            not isinstance(value, int)
            and (not isinstance(value, str) or not value.strip().isdigit())
        ):
            raise ValueError("Cada aparato debe tener un ID entero positivo.")

        inventario_id = int(value)
        if inventario_id <= 0:
            raise ValueError("Cada aparato debe tener un ID entero positivo.")
        if inventario_id in vistos:
            raise ValueError("La selección de aparatos contiene IDs duplicados.")

        vistos.add(inventario_id)
        ids.append(inventario_id)

    # Mantener consistente el campo legacy con el principal. Se permite
    # omitirlo porque el backend toma el primer ID de la lista validada.
    principal = data.get("aparato_id")
    if principal not in (None, ""):
        if isinstance(principal, bool) or (
            not isinstance(principal, int)
            and (
                not isinstance(principal, str)
                or not principal.strip().isdigit()
            )
        ) or int(principal) != ids[0]:
            raise ValueError(
                "aparato_id debe coincidir con el primer aparato de aparatos_ids."
            )

    return TIPO_TRABAJO_TAPIZADO, ids


def registrar_vinculos_tapizado(*, ticket, aparatos_ids, actor):
    """Agrega vínculos y auditoría sin commit.

    La ruta es la autoridad de la transacción, con o sin imagen adjunta.
    """
    if not aparatos_ids or ticket.aparato_id != aparatos_ids[0]:
        raise ValueError("El aparato principal del ticket no coincide.")

    db.session.add_all(
        [
            TicketAparatoORM(ticket_id=ticket.id, inventario_id=inventario_id)
            for inventario_id in aparatos_ids
        ]
    )

    historial = list(ticket.historial_fechas or [])
    historial.append(
        {
            "tipo": "ticket_aparatos_vinculados_v1",
            "origen": "creacion_ticket_tapizado_v1",
            "tipo_trabajo": TIPO_TRABAJO_TAPIZADO,
            "fechaCambio": datetime.now(timezone.utc).isoformat(),
            "cambiadoPor": actor,
            "motivo": "Creación de ticket de tapizado con aparatos vinculados.",
            "aparato_principal_id": aparatos_ids[0],
            "aparatos_ids_anteriores": [],
            "aparatos_ids_nuevos": list(aparatos_ids),
        }
    )
    ticket.historial_fechas = historial
    flag_modified(ticket, "historial_fechas")
