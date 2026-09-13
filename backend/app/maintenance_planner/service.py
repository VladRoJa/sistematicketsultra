from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from app.models.sucursal_model import Sucursal
from app.models.ticket_model import Ticket
from app.utils.pm_permissions import can_pm_execute, can_pm_view
from app.utils.sucursal_audience import (
    SUCURSAL_AUDIENCE_ANALYTICAL,
    SUCURSAL_AUDIENCE_OPERATIONAL,
    TECHNICAL_SUCURSAL_IDS,
    apply_selectable_sucursal_catalog,
    normalize_sucursal_audience,
)
from app.utils.ticket_filters import filtrar_tickets_por_usuario


BUSINESS_TZ = ZoneInfo("America/Tijuana")
MAINTENANCE_DEPARTMENT_ID = 1
ACTIVE_STATES = {"abierto", "en progreso", "por_validar"}
REGIONAL_ROLE = "GERENTE_REGIONAL"


class MaintenancePlannerError(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class MaintenancePlannerAuthorizationError(MaintenancePlannerError):
    status_code = 403


class MaintenancePlannerNotFoundError(MaintenancePlannerError):
    status_code = 404


@dataclass(frozen=True)
class PlannerWindow:
    start: date
    end: date


def _to_business_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BUSINESS_TZ)


def _parse_date(value: str | None, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise MaintenancePlannerError(
            f"{field_name} debe tener formato YYYY-MM-DD."
        ) from exc


def _default_window(reference_date: date) -> PlannerWindow:
    days_since_sunday = (reference_date.weekday() + 1) % 7
    sunday = reference_date - timedelta(days=days_since_sunday)
    return PlannerWindow(start=sunday, end=sunday + timedelta(days=6))


def _resolve_window(start_date: str | None, end_date: str | None) -> PlannerWindow:
    today = datetime.now(BUSINESS_TZ).date()
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")

    if start is None and end is None:
        return _default_window(today)
    if start is None or end is None:
        raise MaintenancePlannerError(
            "start_date y end_date deben enviarse juntos."
        )
    if end < start:
        raise MaintenancePlannerError("end_date no puede ser menor que start_date.")
    if (end - start).days > 31:
        raise MaintenancePlannerError("La ventana máxima del Planner es de 32 días.")
    return PlannerWindow(start=start, end=end)


def _ticket_branch(ticket: Ticket):
    return ticket.sucursal_destino or ticket.sucursal


def _ticket_branch_id(ticket: Ticket) -> int | None:
    value = ticket.sucursal_id_destino or ticket.sucursal_id
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _ticket_branch_name(ticket: Ticket) -> str:
    branch = _ticket_branch(ticket)
    if branch is None:
        return "Sin sucursal"
    return str(
        getattr(branch, "sucursal", None)
        or getattr(branch, "nombre", None)
        or getattr(branch, "nombre_sucursal", None)
        or "Sin sucursal"
    )


def _ticket_due_date(ticket: Ticket) -> date | None:
    dt = _to_business_datetime(ticket.fecha_solucion)
    return dt.date() if dt else None


def _planner_status(ticket: Ticket, today: date) -> str:
    state = str(ticket.estado or "").strip().lower()
    if state == "finalizado":
        return "FINALIZADO"

    due = _ticket_due_date(ticket)
    if due is None:
        return "SIN_FECHA"
    if due < today:
        return "VENCIDO"
    if due == today:
        return "HOY"
    return "PROGRAMADO"


def _calendar_ticket_sort_key(row: dict) -> tuple[int, int]:
    """Prioriza mayor criticidad dentro de cada día del calendario."""

    try:
        criticality = int(row.get("criticidad") or 0)
    except (TypeError, ValueError):
        criticality = 0

    try:
        ticket_id = int(row.get("ticket_id") or 0)
    except (TypeError, ValueError):
        ticket_id = 0

    return (-criticality, ticket_id)


def _iso_business(value: datetime | None) -> str | None:
    resolved = _to_business_datetime(value)
    return resolved.isoformat() if resolved else None


def _serialize_ticket(ticket: Ticket, today: date) -> dict:
    due_dt = _to_business_datetime(ticket.fecha_solucion)
    inventory = ticket.inventario
    family = ticket.familia_equipo
    failure = ticket.falla_mantenimiento
    branch = _ticket_branch(ticket)

    history = [
        {**item}
        for item in (ticket.historial_fechas or [])
        if isinstance(item, dict)
    ]

    return {
        "ticket_id": ticket.id,
        "estado": ticket.estado,
        "planner_status": _planner_status(ticket, today),
        "criticidad": ticket.criticidad,
        "descripcion": ticket.descripcion,
        "username": ticket.username,
        "sucursal_id": _ticket_branch_id(ticket),
        "sucursal": _ticket_branch_name(ticket),
        "sucursal_is_demo": bool(getattr(branch, "is_demo", False)),
        "asignado_a": ticket.asignado_a,
        "fecha_creacion": _iso_business(ticket.fecha_creacion),
        "fecha_en_progreso": _iso_business(ticket.fecha_en_progreso),
        "fecha_finalizado": _iso_business(ticket.fecha_finalizado),
        "fecha_solucion": due_dt.isoformat() if due_dt else None,
        "fecha_solucion_date": due_dt.date().isoformat() if due_dt else None,
        "historial_fechas": history,
        "aparato_id": ticket.aparato_id,
        "equipo": (
            getattr(inventory, "nombre", None)
            or ticket.equipo
            or ticket.detalle
            or "Sin equipo"
        ),
        "codigo_interno": getattr(inventory, "codigo_interno", None),
        "familia": getattr(family, "nombre", None),
        "falla": getattr(failure, "nombre", None),
        "problema_detectado": ticket.problema_detectado,
        "condicion_operativa": ticket.condicion_operativa,
        "ubicacion": ticket.ubicacion,
        "categoria": ticket.categoria,
        "subcategoria": ticket.subcategoria,
        "detalle": ticket.detalle,
        "necesita_refaccion": bool(ticket.necesita_refaccion),
        "descripcion_refaccion": ticket.descripcion_refaccion or None,
        "refaccion_definida_por_jefe": bool(ticket.refaccion_definida_por_jefe),
        "estado_cierre": ticket.estado_cierre,
        "motivo_rechazo_cierre": ticket.motivo_rechazo_cierre,
        "costo_solucion": (
            float(ticket.costo_solucion)
            if ticket.costo_solucion is not None
            else None
        ),
        "notas_cierre": ticket.notas_cierre,
        "url_evidencia": ticket.url_evidencia,
    }


def _effective_ticket_branch_id_expression():
    return func.coalesce(Ticket.sucursal_id_destino, Ticket.sucursal_id)


def _user_role(user) -> str:
    return str(getattr(user, "rol", "") or "").strip().upper()


def _user_scope_branch_ids(user) -> list[int]:
    branch_ids: set[int] = set()
    for value in (getattr(user, "sucursales_ids", None) or []):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in TECHNICAL_SUCURSAL_IDS:
            branch_ids.add(parsed)
    return sorted(branch_ids)


def _apply_planner_role_scope(query, user):
    """Endurece el scope del Planner sin alterar la semántica general de Tickets.

    ``filtrar_tickets_por_usuario`` conserva un fallback por creador útil en la
    pantalla general de Tickets. Para un GERENTE_REGIONAL, el Planner representa
    estrictamente su pool regional, por lo que un ticket creado fuera de ese pool
    no debe entrar al board.
    """

    if _user_role(user) != REGIONAL_ROLE:
        return query

    branch_ids = _user_scope_branch_ids(user)
    if not branch_ids:
        return query.filter(False)

    return query.filter(
        _effective_ticket_branch_id_expression().in_(branch_ids)
    )


def _base_query(user, *, audience: str):
    if not can_pm_view(user):
        raise MaintenancePlannerAuthorizationError(
            "No tienes permiso para consultar el Planner de Mantenimiento."
        )

    branch_id = _effective_ticket_branch_id_expression()
    query = filtrar_tickets_por_usuario(user).filter(
        Ticket.departamento_id == MAINTENANCE_DEPARTMENT_ID,
        ~branch_id.in_(tuple(sorted(TECHNICAL_SUCURSAL_IDS))),
    )
    query = _apply_planner_role_scope(query, user)

    if audience == SUCURSAL_AUDIENCE_ANALYTICAL:
        query = query.filter(
            Ticket.sucursal_destino.has(Sucursal.is_demo.is_(False))
        )

    return query


def _branch_catalog_ids(user, query) -> list[int]:
    """Resuelve el universo del selector antes de filtros del board.

    Para regionales, el catálogo nace de ``sucursales_ids`` y no de los tickets
    existentes. Así una sucursal asignada sigue visible aunque tenga cero tickets.
    Los demás perfiles conservan el comportamiento derivado del query autorizado.
    """

    if _user_role(user) == REGIONAL_ROLE:
        return _user_scope_branch_ids(user)

    branch_id_expr = _effective_ticket_branch_id_expression().label("branch_id")
    branch_rows = query.with_entities(branch_id_expr).distinct().all()
    return sorted(
        {
            int(row[0])
            for row in branch_rows
            if row[0] is not None
        }
    )


def _build_authorized_branch_catalog(user, query, *, audience: str) -> list[dict]:
    """Devuelve sedes visibles sin depender del filtro actual del board."""

    branch_ids = _branch_catalog_ids(user, query)
    if not branch_ids:
        return []

    branch_query = Sucursal.query.filter(Sucursal.sucursal_id.in_(branch_ids))
    branch_query = apply_selectable_sucursal_catalog(
        branch_query,
        audience=audience,
    )
    branches = branch_query.order_by(Sucursal.sucursal.asc()).all()

    return [
        {
            "id": int(branch.sucursal_id),
            "name": str(branch.sucursal),
            "is_demo": bool(branch.is_demo),
        }
        for branch in branches
    ]


def build_planner_board(
    user,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    branch_ids: list[int] | None = None,
    state: str | None = None,
    audience: str = SUCURSAL_AUDIENCE_OPERATIONAL,
) -> dict:
    window = _resolve_window(start_date, end_date)
    today = datetime.now(BUSINESS_TZ).date()

    try:
        normalized_audience = normalize_sucursal_audience(
            audience,
            default=SUCURSAL_AUDIENCE_OPERATIONAL,
        )
    except ValueError as exc:
        raise MaintenancePlannerError(str(exc)) from exc

    base_query = _base_query(user, audience=normalized_audience)
    branches = _build_authorized_branch_catalog(
        user,
        base_query,
        audience=normalized_audience,
    )
    query = base_query

    normalized_branch_ids = sorted(
        {
            int(value)
            for value in (branch_ids or [])
            if str(value).strip().isdigit() and int(value) > 0
        }
    )
    if normalized_branch_ids:
        query = query.filter(
            _effective_ticket_branch_id_expression().in_(normalized_branch_ids)
        )

    normalized_state = str(state or "").strip().lower()
    if normalized_state == "activos":
        query = query.filter(Ticket.estado.in_(ACTIVE_STATES))
    elif normalized_state and normalized_state != "todos":
        allowed_states = ACTIVE_STATES | {"finalizado"}
        if normalized_state not in allowed_states:
            raise MaintenancePlannerError("estado inválido para el Planner.")
        query = query.filter(Ticket.estado == normalized_state)

    tickets = query.order_by(Ticket.fecha_solucion.asc().nullsfirst(), Ticket.id.asc()).all()
    rows = [_serialize_ticket(ticket, today) for ticket in tickets]

    active_rows = [row for row in rows if str(row["estado"]).lower() in ACTIVE_STATES]
    week_rows = [
        row
        for row in rows
        if row["fecha_solucion_date"]
        and window.start.isoformat() <= row["fecha_solucion_date"] <= window.end.isoformat()
    ]

    unscheduled = [row for row in active_rows if row["planner_status"] == "SIN_FECHA"]
    overdue = [row for row in active_rows if row["planner_status"] == "VENCIDO"]
    today_rows = [row for row in active_rows if row["planner_status"] == "HOY"]
    scheduled_future = [
        row for row in active_rows if row["planner_status"] == "PROGRAMADO"
    ]

    days = []
    current = window.start
    while current <= window.end:
        date_iso = current.isoformat()
        day_items = sorted(
            (
                row
                for row in week_rows
                if row["fecha_solucion_date"] == date_iso
            ),
            key=_calendar_ticket_sort_key,
        )
        days.append(
            {
                "date": date_iso,
                "is_today": current == today,
                "items": day_items,
                "total": len(day_items),
            }
        )
        current += timedelta(days=1)

    return {
        "module": "maintenance_planner",
        "version": "v2",
        "audience": normalized_audience,
        "window": {
            "start_date": window.start.isoformat(),
            "end_date": window.end.isoformat(),
            "today": today.isoformat(),
        },
        "metrics": {
            "active": len(active_rows),
            "overdue": len(overdue),
            "today": len(today_rows),
            "week": len(week_rows),
            "unscheduled": len(unscheduled),
            "needs_spare_part": sum(
                1 for row in active_rows if row["necesita_refaccion"]
            ),
        },
        "branches": branches,
        "days": days,
        "overdue": overdue,
        "unscheduled": unscheduled,
        "today_items": today_rows,
        "future": scheduled_future,
        "permissions": {
            "can_view": True,
            "can_schedule": can_pm_execute(user),
        },
    }


def _scoped_maintenance_ticket(ticket_id: int, user) -> Ticket:
    if not can_pm_execute(user):
        raise MaintenancePlannerAuthorizationError(
            "No tienes permiso para programar tickets de Mantenimiento."
        )

    ticket = (
        filtrar_tickets_por_usuario(user)
        .filter(
            Ticket.id == ticket_id,
            Ticket.departamento_id == MAINTENANCE_DEPARTMENT_ID,
        )
        .first()
    )
    if ticket is None:
        raise MaintenancePlannerNotFoundError(
            "Ticket de Mantenimiento no encontrado o fuera de tu alcance."
        )
    if str(ticket.estado or "").strip().lower() == "finalizado":
        raise MaintenancePlannerError("No se puede programar un ticket finalizado.")
    return ticket


def schedule_ticket(ticket_id: int, user, *, due_date: str, reason: str) -> Ticket:
    ticket = _scoped_maintenance_ticket(ticket_id, user)
    target_date = _parse_date(due_date, "due_date")
    reason = str(reason or "").strip()
    if target_date is None:
        raise MaintenancePlannerError("due_date es obligatorio.")
    if not reason:
        raise MaintenancePlannerError("reason es obligatorio.")

    local_due = datetime.combine(target_date, time(hour=7), tzinfo=BUSINESS_TZ)
    due_utc = local_due.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)

    ticket.fecha_solucion = due_utc
    if str(ticket.estado or "").strip().lower() == "abierto":
        ticket.estado = "en progreso"
    if ticket.fecha_en_progreso is None:
        ticket.fecha_en_progreso = now_utc

    history = list(ticket.historial_fechas or [])
    history.append(
        {
            "fecha": due_utc.isoformat(),
            "cambiadoPor": str(getattr(user, "username", "") or "").strip(),
            "fechaCambio": now_utc.isoformat(),
            "motivo": reason,
            "origen": "maintenance_planner_v2",
        }
    )
    history.sort(
        key=lambda item: str(item.get("fechaCambio") or item.get("fecha") or ""),
        reverse=True,
    )
    ticket.historial_fechas = history
    flag_modified(ticket, "historial_fechas")
    return ticket
