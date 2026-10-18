"""Asignación y compromiso transaccionales de Tickets V1 de Mantenimiento.

El endpoint HTTP hace exactamente un commit. No reabre cierres ni habilita
bitácoras/validaciones. El alcance individual se valida desde la DB.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm.attributes import flag_modified

from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.utils.tickets_maintenance_permissions import (
    ADMIN_ROLES,
    ASSIGNED_ONLY_ELIGIBLE_ROLES,
    has_maintenance_coordination_permission,
)
from app.utils.pm_permissions import normalize_pm_role


BUSINESS_TZ = ZoneInfo("America/Tijuana")
MAINTENANCE_DEPARTMENT_ID = 1
COORDINATABLE_STATES = frozenset({"abierto", "en progreso"})
ATTENTION_MODES = frozenset({"INTERNA", "EXTERNA"})
MAINTENANCE_WORK_REVIEW_PENDING = "pendiente_revision_coord"


class TicketCoordinationError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TicketCoordinationForbidden(TicketCoordinationError):
    status_code = 403


class TicketCoordinationNotFound(TicketCoordinationError):
    status_code = 404


def _normalized_scope(user) -> set[int]:
    result = set()
    for branch_id in (getattr(user, "sucursales_ids", None) or []):
        try:
            result.add(int(branch_id))
        except (TypeError, ValueError):
            continue
    return result


def _can_coordinate_branch(user, branch_id: int) -> bool:
    if normalize_pm_role(getattr(user, "rol", None)) in ADMIN_ROLES:
        return True
    return int(branch_id) in _normalized_scope(user)


def _ticket_branch_id(ticket: Ticket) -> int:
    return int(ticket.sucursal_id_destino or ticket.sucursal_id)


def _invalidate_work_review_on_assignment_change(
    ticket: Ticket,
    previous_mode: str | None,
    previous_assignee: str | None,
    next_mode: str | None,
    next_assignee: str | None,
) -> bool:
    """Anula la terminación anterior cuando cambia proveedor o técnico."""
    if getattr(ticket, "estado_cierre", None) != MAINTENANCE_WORK_REVIEW_PENDING:
        return False

    if (
        previous_mode == next_mode
        and str(previous_assignee or "").strip().casefold()
        == str(next_assignee or "").strip().casefold()
    ):
        return False

    ticket.estado_cierre = None
    return True


def list_maintenance_assignees(user) -> list[dict]:
    """Catálogo acotado a personal interno de Mantenimiento, sin contraseñas."""

    if not has_maintenance_coordination_permission(user):
        raise TicketCoordinationForbidden("Sin permiso para coordinar Mantenimiento.")

    persons = (
        UserORM.query
        .filter(UserORM.department_id == MAINTENANCE_DEPARTMENT_ID)
        .order_by(UserORM.username.asc())
        .all()
    )
    return [{"id": person.id, "username": person.username} for person in persons]


def prepare_maintenance_coordination(
    ticket_id: int,
    user,
    payload: dict,
    *,
    now: datetime | None = None,
) -> Ticket:
    """Valida y aplica todos los campos; no emite notificaciones ni commit."""

    if not has_maintenance_coordination_permission(user):
        raise TicketCoordinationForbidden("Sin permiso para coordinar Mantenimiento.")

    ticket = (
        Ticket.query
        .filter(
            Ticket.id == ticket_id,
            Ticket.departamento_id == MAINTENANCE_DEPARTMENT_ID,
        )
        .first()
    )
    if ticket is None or not _can_coordinate_branch(user, _ticket_branch_id(ticket)):
        raise TicketCoordinationNotFound(
            "Ticket de Mantenimiento inexistente o fuera de alcance."
        )

    if str(ticket.estado or "").strip().lower() not in COORDINATABLE_STATES:
        raise TicketCoordinationError(
            "Solo se puede coordinar un ticket abierto o en progreso."
        )

    if not isinstance(payload, dict):
        raise TicketCoordinationError("El cuerpo debe ser un objeto JSON.")

    reason = str(payload.get("motivo") or "").strip()
    if not reason:
        raise TicketCoordinationError("El motivo es obligatorio.")

    due_date_raw = payload.get("due_date")
    try:
        due_date = date.fromisoformat(due_date_raw)
    except (TypeError, ValueError):
        raise TicketCoordinationError("due_date debe tener formato YYYY-MM-DD.")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    if due_date < current_time.astimezone(BUSINESS_TZ).date():
        raise TicketCoordinationError("La fecha compromiso no puede ser anterior a hoy.")

    attention_mode = str(payload.get("tipo_atencion") or "").strip().upper()
    if attention_mode not in ATTENTION_MODES:
        raise TicketCoordinationError("Selecciona INTERNA o EXTERNA.")

    assignee_id = payload.get("asignado_user_id")
    assigned_username = None
    if attention_mode == "INTERNA":
        if not isinstance(assignee_id, int) or isinstance(assignee_id, bool):
            raise TicketCoordinationError(
                "Selecciona un usuario de Mantenimiento como responsable."
            )
        assignee = UserORM.get_by_id(assignee_id)
        if assignee is None or int(assignee.department_id or 0) != MAINTENANCE_DEPARTMENT_ID:
            raise TicketCoordinationError(
                "El responsable debe ser un usuario real del departamento Mantenimiento."
            )
        assigned_username = assignee.username
    elif assignee_id is not None:
        raise TicketCoordinationError(
            "Atención EXTERNA no acepta responsable de usuario Suite."
        )

    if "necesita_refaccion" in payload:
        if not isinstance(payload["necesita_refaccion"], bool):
            raise TicketCoordinationError("necesita_refaccion debe ser booleano.")
        needs_part = payload["necesita_refaccion"]
        description = str(payload.get("descripcion_refaccion") or "").strip()
        if len(description) > 500:
            raise TicketCoordinationError(
                "descripcion_refaccion no puede superar 500 caracteres."
            )
    else:
        needs_part = None
        description = None

    due_utc = datetime.combine(
        due_date, time(hour=7), tzinfo=BUSINESS_TZ
    ).astimezone(timezone.utc)

    previous_assignment = ticket.asignado_a
    previous_mode = ticket.tipo_atencion
    previous_due = ticket.fecha_solucion
    previous_state = ticket.estado

    ticket.tipo_atencion = attention_mode
    ticket.asignado_a = assigned_username
    review_invalidated = _invalidate_work_review_on_assignment_change(
        ticket, previous_mode, previous_assignment, attention_mode, assigned_username,
    )
    ticket.fecha_solucion = due_utc
    if str(ticket.estado or "").strip().lower() == "abierto":
        ticket.estado = "en progreso"
    if ticket.fecha_en_progreso is None:
        ticket.fecha_en_progreso = current_time

    if needs_part is not None:
        ticket.necesita_refaccion = needs_part
        ticket.descripcion_refaccion = description if needs_part else None

    history = list(ticket.historial_fechas or [])
    history.append({
        "tipo": "maintenance_coordination_v1",
        "origen": "tickets_v1",
        "fecha": due_utc.isoformat(),
        "fechaCambio": current_time.isoformat(),
        "cambiadoPor": str(getattr(user, "username", "") or "").strip(),
        "motivo": reason,
        "tipo_atencion_anterior": previous_mode,
        "tipo_atencion_nuevo": attention_mode,
        "asignado_anterior": previous_assignment,
        "asignado_nuevo": assigned_username,
        "revision_tecnica_invalidada": review_invalidated,
        "fecha_compromiso_anterior": (
            previous_due.isoformat() if previous_due else None
        ),
        "estado_anterior": previous_state,
        "estado_nuevo": ticket.estado,
    })
    history.sort(
        key=lambda item: str(item.get("fechaCambio") or item.get("fecha") or ""),
        reverse=True,
    )
    ticket.historial_fechas = history
    flag_modified(ticket, "historial_fechas")
    return ticket



def prepare_maintenance_work_completion(
    ticket_id: int,
    user,
    payload: dict,
    *,
    now: datetime | None = None,
) -> Ticket:
    """El técnico asignado marca trabajo terminado sin solicitar cierre.

    Conserva estado='en progreso' y fecha/costo/solución intactos; el
    coordinador revisará antes de solicitar conformidad del gerente.
    No hace commit ni envía notificaciones.
    """

    role = normalize_pm_role(getattr(user, "rol", None))
    if (
        role not in ASSIGNED_ONLY_ELIGIBLE_ROLES
        or int(getattr(user, "department_id", 0) or 0) != MAINTENANCE_DEPARTMENT_ID
    ):
        raise TicketCoordinationForbidden(
            "Solo un técnico de Mantenimiento puede terminar su trabajo."
        )

    ticket = (
        Ticket.query
        .filter(
            Ticket.id == ticket_id,
            Ticket.departamento_id == MAINTENANCE_DEPARTMENT_ID,
        )
        .first()
    )
    if (
        ticket is None
        or str(getattr(ticket, "asignado_a", "") or "").strip().casefold()
        != str(getattr(user, "username", "") or "").strip().casefold()
    ):
        raise TicketCoordinationNotFound(
            "Ticket de Mantenimiento inexistente o no asignado a este técnico."
        )

    if str(ticket.tipo_atencion or "").strip().upper() != "INTERNA":
        raise TicketCoordinationError(
            "Solo la atención INTERNA permite marcar trabajo terminado."
        )
    if str(ticket.estado or "").strip().lower() != "en progreso":
        raise TicketCoordinationError(
            "Solo se puede terminar un trabajo en progreso."
        )
    if getattr(ticket, "estado_cierre", None):
        raise TicketCoordinationError(
            "El ticket ya tiene una etapa de revisión o cierre activa."
        )

    if not isinstance(payload, dict):
        raise TicketCoordinationError("El cuerpo debe ser un objeto JSON.")
    if set(payload) - {"notas_trabajo"}:
        raise TicketCoordinationError(
            "Trabajo terminado solo admite notas_trabajo."
        )
    notes = payload.get("notas_trabajo")
    if not isinstance(notes, str) or not 1 <= len(notes.strip()) <= 2000:
        raise TicketCoordinationError(
            "Describe el trabajo realizado (1-2000 caracteres)."
        )

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    ticket.estado_cierre = MAINTENANCE_WORK_REVIEW_PENDING
    history = list(ticket.historial_fechas or [])
    history.append({
        "tipo": "maintenance_work_completed_v1",
        "origen": "tickets_v1",
        "fechaCambio": current_time.isoformat(),
        "cambiadoPor": str(user.username).strip(),
        "motivo": notes.strip(),
        "tipo_atencion": "INTERNA",
        "asignado_a": ticket.asignado_a,
        "estado": ticket.estado,
        "estado_cierre_nuevo": MAINTENANCE_WORK_REVIEW_PENDING,
    })
    history.sort(
        key=lambda item: str(item.get("fechaCambio") or item.get("fecha") or ""),
        reverse=True,
    )
    ticket.historial_fechas = history
    flag_modified(ticket, "historial_fechas")
    return ticket


def prepare_maintenance_work_return(
    ticket_id: int,
    user,
    payload: dict,
    *,
    now: datetime | None = None,
) -> Ticket:
    """Coordinación devuelve una reparación interna sin alterar otros campos."""

    if not has_maintenance_coordination_permission(user):
        raise TicketCoordinationForbidden(
            "Sin permiso para revisar trabajos de Mantenimiento."
        )

    ticket = (
        Ticket.query
        .filter(
            Ticket.id == ticket_id,
            Ticket.departamento_id == MAINTENANCE_DEPARTMENT_ID,
        )
        .first()
    )
    if ticket is None or not _can_coordinate_branch(user, _ticket_branch_id(ticket)):
        raise TicketCoordinationNotFound(
            "Ticket de Mantenimiento inexistente o fuera de alcance."
        )

    if (
        str(ticket.tipo_atencion or "").strip().upper() != "INTERNA"
        or str(ticket.estado or "").strip().lower() != "en progreso"
        or str(getattr(ticket, "estado_cierre", "") or "").strip().lower()
        != MAINTENANCE_WORK_REVIEW_PENDING
    ):
        raise TicketCoordinationError(
            "Solo se puede devolver un trabajo interno pendiente de revisión."
        )
    if not isinstance(payload, dict) or set(payload) - {"motivo"}:
        raise TicketCoordinationError("La devolución solo admite un motivo.")
    reason = payload.get("motivo")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise TicketCoordinationError(
            "Describe por qué se devuelve el trabajo (1-500 caracteres)."
        )

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    ticket.estado_cierre = None
    history = list(ticket.historial_fechas or [])
    history.append({
        "tipo": "maintenance_work_returned_v1",
        "origen": "tickets_v1",
        "fechaCambio": current_time.isoformat(),
        "cambiadoPor": str(getattr(user, "username", "") or "").strip(),
        "motivo": reason.strip(),
        "tipo_atencion": "INTERNA",
        "asignado_a": ticket.asignado_a,
        "estado": ticket.estado,
        "estado_cierre_anterior": MAINTENANCE_WORK_REVIEW_PENDING,
        "estado_cierre_nuevo": None,
    })
    history.sort(
        key=lambda item: str(item.get("fechaCambio") or item.get("fecha") or ""),
        reverse=True,
    )
    ticket.historial_fechas = history
    flag_modified(ticket, "historial_fechas")
    return ticket


def prepare_maintenance_reassignment(
    ticket_id: int,
    user,
    payload: dict,
    *,
    now: datetime | None = None,
) -> Ticket:
    """Reasigna exclusivamente atención/responsable, con historial auditable.

    Deliberadamente no modifica fecha compromiso, fecha en progreso, estado,
    refacción ni otras propiedades del ticket.
    """

    if not has_maintenance_coordination_permission(user):
        raise TicketCoordinationForbidden("Sin permiso para reasignar Mantenimiento.")

    ticket = (
        Ticket.query
        .filter(
            Ticket.id == ticket_id,
            Ticket.departamento_id == MAINTENANCE_DEPARTMENT_ID,
        )
        .first()
    )
    if ticket is None or not _can_coordinate_branch(user, _ticket_branch_id(ticket)):
        raise TicketCoordinationNotFound(
            "Ticket de Mantenimiento inexistente o fuera de alcance."
        )

    if str(ticket.estado or "").strip().lower() not in COORDINATABLE_STATES:
        raise TicketCoordinationError(
            "Solo se puede reasignar un ticket abierto o en progreso."
        )

    if not isinstance(payload, dict):
        raise TicketCoordinationError("El cuerpo debe ser un objeto JSON.")

    # El contrato de esta ruta es intencionadamente estrecho.
    unexpected = set(payload) - {"motivo", "tipo_atencion", "asignado_user_id"}
    if unexpected:
        raise TicketCoordinationError(
            "La reasignación no admite cambios de fecha, estado ni refacción."
        )

    reason = payload.get("motivo")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise TicketCoordinationError("Indica un motivo de reasignación (máximo 500 caracteres).")
    reason = reason.strip()

    attention_mode = payload.get("tipo_atencion")
    if attention_mode not in ATTENTION_MODES:
        raise TicketCoordinationError("Selecciona atención INTERNA o EXTERNA.")

    assignee_id = payload.get("asignado_user_id")
    assigned_username = None
    if attention_mode == "INTERNA":
        if not isinstance(assignee_id, int) or isinstance(assignee_id, bool):
            raise TicketCoordinationError(
                "Selecciona un usuario de Mantenimiento como nuevo responsable."
            )
        assignee = UserORM.get_by_id(assignee_id)
        if assignee is None or int(assignee.department_id or 0) != MAINTENANCE_DEPARTMENT_ID:
            raise TicketCoordinationError(
                "El responsable debe pertenecer a Mantenimiento."
            )
        assigned_username = assignee.username
    elif assignee_id is not None:
        raise TicketCoordinationError(
            "Atención EXTERNA no acepta un usuario Suite."
        )

    previous_username = ticket.asignado_a
    previous_mode = ticket.tipo_atencion
    if (previous_mode == attention_mode and
        str(previous_username or "").casefold() == str(assigned_username or "").casefold()):
        raise TicketCoordinationError("Selecciona un responsable distinto al actual.")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    ticket.tipo_atencion = attention_mode
    ticket.asignado_a = assigned_username
    review_invalidated = _invalidate_work_review_on_assignment_change(
        ticket, previous_mode, previous_username, attention_mode, assigned_username,
    )

    history = list(ticket.historial_fechas or [])
    history.append({
        "tipo": "maintenance_reassignment_v1",
        "origen": "tickets_v1",
        "fechaCambio": current_time.isoformat(),
        "cambiadoPor": str(getattr(user, "username", "") or "").strip(),
        "motivo": reason,
        "tipo_atencion_anterior": previous_mode,
        "tipo_atencion_nuevo": attention_mode,
        "asignado_anterior": previous_username,
        "asignado_nuevo": assigned_username,
        "revision_tecnica_invalidada": review_invalidated,
    })
    history.sort(
        key=lambda item: str(item.get("fechaCambio") or item.get("fecha") or ""),
        reverse=True,
    )
    ticket.historial_fechas = history
    flag_modified(ticket, "historial_fechas")
    return ticket
