from datetime import datetime, timezone

from dateutil import parser
from sqlalchemy.orm.attributes import flag_modified

from app.models.inventario import InventarioGeneral
from app.models.mantenimiento_equipo import (
    FallaMantenimientoORM,
    FamiliaEquipoORM,
)
from app.models.ticket_model import Ticket
from app.utils.ticket_filters import filtrar_tickets_por_usuario


MAINTENANCE_DEPARTMENT_ID = 1
MAINTENANCE_CAPTURE_ROLE = "MANTENIMIENTO"
OPERATING_CONDITIONS = {"TRABAJA", "NO_TRABAJA"}


class MantenimientoEquiposError(Exception):
    status_code = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class MantenimientoEquiposAuthorizationError(MantenimientoEquiposError):
    status_code = 403


class MantenimientoEquiposNotFoundError(MantenimientoEquiposError):
    status_code = 404


def _normalized_role(user):
    return str(getattr(user, "rol", "") or "").strip().upper()


def _integer_id(value, field_name):
    if isinstance(value, bool):
        raise MantenimientoEquiposError(f"{field_name} debe ser numérico.")

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise MantenimientoEquiposError(f"{field_name} debe ser numérico.")

    if parsed <= 0:
        raise MantenimientoEquiposError(f"{field_name} debe ser mayor que cero.")

    return parsed


def _parse_solution_date(value):
    if not value:
        raise MantenimientoEquiposError("fecha_solucion es obligatoria.")

    try:
        parsed = parser.isoparse(str(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise MantenimientoEquiposError(
            f"fecha_solucion inválida: {exc}"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _history_sort_key(item):
    value = (
        item.get("fechaCambio")
        or item.get("fecha_cambio")
        or item.get("fecha")
    )
    try:
        parsed = parser.isoparse(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return datetime.min.replace(tzinfo=timezone.utc)


def puede_capturar_diagnostico_mantenimiento(user):
    if not user:
        return False

    try:
        department_id = int(getattr(user, "department_id", 0) or 0)
    except (TypeError, ValueError):
        return False

    return (
        _normalized_role(user) == MAINTENANCE_CAPTURE_ROLE
        and department_id == MAINTENANCE_DEPARTMENT_ID
    )


def listar_familias_activas():
    return (
        FamiliaEquipoORM.query
        .filter(FamiliaEquipoORM.activo.is_(True))
        .order_by(FamiliaEquipoORM.nombre.asc())
        .all()
    )


def listar_fallas_activas(familia_equipo_id):
    return (
        FallaMantenimientoORM.query
        .filter(
            FallaMantenimientoORM.familia_equipo_id == familia_equipo_id,
            FallaMantenimientoORM.activo.is_(True),
        )
        .order_by(
            FallaMantenimientoORM.orden.asc(),
            FallaMantenimientoORM.nombre.asc(),
        )
        .all()
    )


def _ticket_en_scope(ticket_id, user):
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        raise MantenimientoEquiposNotFoundError("Ticket no encontrado.")

    ticket_visible = (
        filtrar_tickets_por_usuario(user)
        .filter(Ticket.id == ticket_id)
        .first()
    )
    if not ticket_visible:
        raise MantenimientoEquiposAuthorizationError(
            "No tienes alcance para actualizar este ticket."
        )

    return ticket


def _validate_structured_diagnosis(ticket, payload):
    structured_keys = (
        "falla_mantenimiento_id",
        "condicion_operativa",
    )

    if not ticket.aparato_id:
        if any(payload.get(key) is not None for key in structured_keys):
            raise MantenimientoEquiposError(
                "Un ticket sin aparato no puede recibir diagnóstico estructurado."
            )
        return None, None, None, None

    inventario = ticket.inventario or InventarioGeneral.query.get(ticket.aparato_id)
    if not inventario:
        raise MantenimientoEquiposNotFoundError(
            "El aparato asociado al ticket no existe."
        )

    if not getattr(inventario, "familia_equipo_id", None):
        raise MantenimientoEquiposError(
            "Este aparato no tiene una familia asignada. "
            "Clasifícalo primero desde Inventario."
        )

    family_id = _integer_id(
        inventario.familia_equipo_id,
        "inventario_general.familia_equipo_id",
    )
    failure_id = _integer_id(
        payload.get("falla_mantenimiento_id"),
        "falla_mantenimiento_id",
    )
    condition = str(payload.get("condicion_operativa") or "").strip().upper()
    if condition not in OPERATING_CONDITIONS:
        raise MantenimientoEquiposError(
            "condicion_operativa debe ser TRABAJA o NO_TRABAJA."
        )

    family = FamiliaEquipoORM.query.get(family_id)
    if not family:
        raise MantenimientoEquiposNotFoundError("Familia de equipo no encontrada.")
    if not family.activo:
        raise MantenimientoEquiposError("La familia de equipo está inactiva.")

    failure = FallaMantenimientoORM.query.get(failure_id)
    if not failure:
        raise MantenimientoEquiposNotFoundError(
            "Falla de mantenimiento no encontrada."
        )
    if not failure.activo:
        raise MantenimientoEquiposError("La falla de mantenimiento está inactiva.")
    if int(failure.familia_equipo_id) != int(family.id):
        raise MantenimientoEquiposError(
            "La falla seleccionada no pertenece a la familia del equipo."
        )

    return inventario, family, failure, condition


def _apply_spare_part(ticket, payload):
    if "necesita_refaccion" not in payload:
        if "descripcion_refaccion" in payload:
            raise MantenimientoEquiposError(
                "necesita_refaccion es obligatorio al enviar descripción de refacción."
            )
        return

    requires_spare = payload.get("necesita_refaccion")
    if not isinstance(requires_spare, bool):
        raise MantenimientoEquiposError(
            "necesita_refaccion debe ser booleano."
        )

    description = str(payload.get("descripcion_refaccion") or "").strip()
    ticket.necesita_refaccion = requires_spare
    ticket.descripcion_refaccion = description if requires_spare else None
    ticket.refaccion_definida_por_jefe = True


def preparar_backfill_ticket_historico(
    ticket_id,
    familia_key,
    falla_key,
    condicion_operativa,
):
    """Prepara un backfill histórico de un solo ticket, sin commit."""
    ticket_id = _integer_id(ticket_id, "ticket_id")
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        raise MantenimientoEquiposNotFoundError("Ticket no encontrado.")
    if not ticket.aparato_id:
        raise MantenimientoEquiposError(
            "El ticket histórico no tiene aparato asociado."
        )

    if any(
        value is not None
        for value in (
            ticket.familia_equipo_id,
            ticket.falla_mantenimiento_id,
            ticket.condicion_operativa,
        )
    ):
        raise MantenimientoEquiposError(
            "El ticket ya contiene captura estructurada; no se sobrescribirá."
        )

    family_key = str(familia_key or "").strip().upper()
    failure_key = str(falla_key or "").strip().upper()
    condition = str(condicion_operativa or "").strip().upper()
    if not family_key:
        raise MantenimientoEquiposError("familia_key es obligatoria.")
    if not failure_key:
        raise MantenimientoEquiposError("falla_key es obligatoria.")
    if condition not in OPERATING_CONDITIONS:
        raise MantenimientoEquiposError(
            "condicion_operativa debe ser TRABAJA o NO_TRABAJA."
        )

    family = FamiliaEquipoORM.query.filter_by(
        key=family_key,
        activo=True,
    ).first()
    if not family:
        raise MantenimientoEquiposNotFoundError(
            "Familia de equipo activa no encontrada."
        )

    failure = FallaMantenimientoORM.query.filter_by(
        familia_equipo_id=family.id,
        key=failure_key,
        activo=True,
    ).first()
    if not failure:
        raise MantenimientoEquiposNotFoundError(
            "Falla activa no encontrada para la familia indicada."
        )

    ticket.familia_equipo_id = family.id
    ticket.falla_mantenimiento_id = failure.id
    ticket.condicion_operativa = condition
    return ticket


def preparar_compromiso_estructurado(ticket_id, user, payload, now=None):
    """Prepara la operación completa sin commit ni notificaciones."""
    if not puede_capturar_diagnostico_mantenimiento(user):
        raise MantenimientoEquiposAuthorizationError(
            "Sólo MANTENIMIENTO del departamento 1 puede capturar el diagnóstico."
        )

    ticket = _ticket_en_scope(ticket_id, user)
    if int(ticket.departamento_id or 0) != MAINTENANCE_DEPARTMENT_ID:
        raise MantenimientoEquiposAuthorizationError(
            "El ticket no pertenece al departamento de Mantenimiento."
        )
    if str(ticket.estado or "").strip().lower() == "finalizado":
        raise MantenimientoEquiposError(
            "No se puede asignar compromiso a un ticket finalizado."
        )

    if not isinstance(payload, dict):
        raise MantenimientoEquiposError("El cuerpo JSON es inválido.")

    motive = str(payload.get("motivo") or "").strip()
    if not motive:
        raise MantenimientoEquiposError("motivo es obligatorio.")

    solution_date = _parse_solution_date(payload.get("fecha_solucion"))
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    inventario, family, failure, condition = _validate_structured_diagnosis(
        ticket,
        payload,
    )
    if inventario is not None:
        ticket.familia_equipo_id = family.id
        ticket.falla_mantenimiento_id = failure.id
        ticket.condicion_operativa = condition

    _apply_spare_part(ticket, payload)

    ticket.fecha_solucion = solution_date
    ticket.estado = "en progreso"
    if not ticket.fecha_en_progreso:
        ticket.fecha_en_progreso = current_time

    history = list(ticket.historial_fechas or [])
    history.append(
        {
            "fecha": solution_date.isoformat(),
            "cambiadoPor": str(getattr(user, "username", "") or "").strip(),
            "fechaCambio": current_time.isoformat(),
            "motivo": motive,
        }
    )
    history.sort(key=_history_sort_key, reverse=True)
    ticket.historial_fechas = history
    flag_modified(ticket, "historial_fechas")

    return ticket
