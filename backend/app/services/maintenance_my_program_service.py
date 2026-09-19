# backend/app/services/maintenance_my_program_service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.models.maintenance_preventive import MaintenancePersonnelORM
from app.models.ticket_model import Ticket


BUSINESS_TZ = ZoneInfo("America/Tijuana")
MAINTENANCE_DEPARTMENT_ID = 1
ACTIVE_STATES = {"abierto", "en progreso", "por_validar"}


class MaintenanceMyProgramError(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class MaintenanceMyProgramAuthorizationError(MaintenanceMyProgramError):
    status_code = 403


@dataclass(frozen=True)
class ProgramWindow:
    start: date
    end: date


def _business_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BUSINESS_TZ).date()


def _default_window(reference: date) -> ProgramWindow:
    days_since_sunday = (reference.weekday() + 1) % 7
    sunday = reference - timedelta(days=days_since_sunday)
    return ProgramWindow(
        start=sunday,
        end=sunday + timedelta(days=6),
    )


def _parse_window(
    start_date: str | None,
    end_date: str | None,
) -> ProgramWindow:
    today = datetime.now(BUSINESS_TZ).date()

    if not start_date and not end_date:
        return _default_window(today)

    if not start_date or not end_date:
        raise MaintenanceMyProgramError(
            "start_date y end_date deben enviarse juntos."
        )

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise MaintenanceMyProgramError(
            "Las fechas deben tener formato YYYY-MM-DD."
        ) from exc

    if end < start:
        raise MaintenanceMyProgramError(
            "end_date no puede ser menor que start_date."
        )

    if (end - start).days > 31:
        raise MaintenanceMyProgramError(
            "La ventana máxima es de 32 días."
        )

    return ProgramWindow(start=start, end=end)


def _active_personnel(user):
    if user is None:
        return None

    return (
        MaintenancePersonnelORM.query
        .filter(
            MaintenancePersonnelORM.user_id == int(user.id),
            MaintenancePersonnelORM.activo.is_(True),
        )
        .first()
    )


def require_my_program_access(user):
    try:
        department_id = int(getattr(user, "department_id", 0) or 0)
    except (TypeError, ValueError):
        department_id = 0

    if department_id != MAINTENANCE_DEPARTMENT_ID:
        raise MaintenanceMyProgramAuthorizationError(
            "Tu usuario no pertenece al departamento de Mantenimiento."
        )

    personnel = _active_personnel(user)
    if personnel is None:
        raise MaintenanceMyProgramAuthorizationError(
            "Tu usuario no está activo en el catálogo de personal de Mantenimiento."
        )

    return personnel


def _ticket_work_date(ticket: Ticket) -> date | None:
    maintenance_type = (
        str(ticket.tipo_mantenimiento or "CORRECTIVO").strip().upper()
    )

    if maintenance_type == "PREVENTIVO":
        return _business_date(ticket.fecha_programada_actual)

    return _business_date(ticket.fecha_solucion)


def _branch_name(ticket: Ticket) -> str:
    branch = ticket.sucursal_destino or ticket.sucursal
    return str(
        getattr(branch, "sucursal", None)
        or getattr(branch, "nombre", None)
        or "Sin sucursal"
    )


def _serialize_ticket(ticket: Ticket, today: date) -> dict:
    work_date = _ticket_work_date(ticket)
    maintenance_type = (
        str(ticket.tipo_mantenimiento or "CORRECTIVO").strip().upper()
    )
    state = str(ticket.estado or "").strip().lower()

    if state == "por_validar":
        operational_status = "PENDIENTE_VALIDACION"
    elif work_date is None:
        operational_status = "SIN_FECHA"
    elif work_date < today:
        operational_status = "VENCIDO"
    elif work_date == today:
        operational_status = "HOY"
    else:
        operational_status = "PROGRAMADO"

    inventory = ticket.inventario

    return {
        "ticket_id": int(ticket.id),
        "tipo_mantenimiento": maintenance_type,
        "estado": ticket.estado,
        "operational_status": operational_status,
        "fecha_trabajo": work_date.isoformat() if work_date else None,
        "sucursal_id": (
            ticket.sucursal_id_destino or ticket.sucursal_id
        ),
        "sucursal": _branch_name(ticket),
        "inventario_id": ticket.aparato_id,
        "codigo_equipo": (
            getattr(inventory, "codigo_interno", None)
            if inventory is not None
            else None
        ),
        "equipo": (
            getattr(inventory, "nombre", None)
            or ticket.equipo
            or ticket.detalle
            or "Sin equipo"
        ),
        "actividad": ticket.descripcion,
        "problema_detectado": ticket.problema_detectado,
        "necesita_refaccion": bool(ticket.necesita_refaccion),
        "descripcion_refaccion": ticket.descripcion_refaccion,
    }


def build_my_program(
    user,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    personnel = require_my_program_access(user)
    window = _parse_window(start_date, end_date)
    today = datetime.now(BUSINESS_TZ).date()

    username = str(getattr(user, "username", "") or "").strip()
    if not username:
        raise MaintenanceMyProgramAuthorizationError(
            "Tu usuario no tiene username operativo."
        )

    tickets = (
        Ticket.query
        .filter(
            Ticket.departamento_id == MAINTENANCE_DEPARTMENT_ID,
            Ticket.estado.in_(ACTIVE_STATES),
            func.lower(Ticket.asignado_a) == username.casefold(),
        )
        .order_by(Ticket.id.asc())
        .all()
    )

    rows = [_serialize_ticket(ticket, today) for ticket in tickets]

    today_items = [
        row
        for row in rows
        if row["fecha_trabajo"] == today.isoformat()
        and row["operational_status"] != "PENDIENTE_VALIDACION"
    ]
    week_items = [
        row
        for row in rows
        if row["fecha_trabajo"]
        and window.start.isoformat()
        <= row["fecha_trabajo"]
        <= window.end.isoformat()
    ]
    overdue = [
        row for row in rows if row["operational_status"] == "VENCIDO"
    ]
    pending_validation = [
        row
        for row in rows
        if row["operational_status"] == "PENDIENTE_VALIDACION"
    ]
    unscheduled = [
        row for row in rows if row["operational_status"] == "SIN_FECHA"
    ]

    sort_key = lambda row: (
        row["fecha_trabajo"] or "9999-12-31",
        row["sucursal"],
        row["ticket_id"],
    )

    return {
        "personnel": {
            "id": int(personnel.id),
            "user_id": int(personnel.user_id),
            "username": username,
            "crew_id": personnel.crew_id,
            "crew": (
                personnel.crew.nombre
                if personnel.crew is not None
                else None
            ),
            "region_id": (
                personnel.crew.region_id
                if personnel.crew is not None
                else None
            ),
        },
        "window": {
            "start_date": window.start.isoformat(),
            "end_date": window.end.isoformat(),
            "today": today.isoformat(),
        },
        "metrics": {
            "today": len(today_items),
            "week": len(week_items),
            "overdue": len(overdue),
            "pending_validation": len(pending_validation),
            "unscheduled": len(unscheduled),
        },
        "today_items": sorted(today_items, key=sort_key),
        "week_items": sorted(week_items, key=sort_key),
        "overdue": sorted(overdue, key=sort_key),
        "pending_validation": sorted(
            pending_validation,
            key=sort_key,
        ),
        "unscheduled": sorted(unscheduled, key=sort_key),
    }
