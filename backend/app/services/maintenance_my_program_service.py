# backend/app/services/maintenance_my_program_service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.models.maintenance_preventive import (
    MaintenancePersonnelORM,
    MaintenancePreventiveScheduleORM,
)
from app.models.ticket_model import Ticket


BUSINESS_TZ = ZoneInfo("America/Tijuana")
MAINTENANCE_DEPARTMENT_ID = 1
ACTIVE_STATES = {"abierto", "en progreso", "por_validar"}
DAILY_CAPACITY_MINUTES = 9 * 60


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


def _add_workdays(start_date: date, workdays: int) -> date:
    result = start_date
    remaining = int(workdays)

    while remaining > 0:
        result += timedelta(days=1)
        if result.weekday() < 5:
            remaining -= 1

    return result


def _projection_dates(
    schedule: MaintenancePreventiveScheduleORM,
    window: ProgramWindow,
    today: date,
) -> list[date]:
    if not bool(getattr(schedule, "active", False)):
        return []

    next_date = getattr(schedule, "next_scheduled_date", None)
    try:
        interval = int(
            getattr(schedule, "repeat_interval_workdays", 0) or 0
        )
    except (TypeError, ValueError):
        return []

    if next_date is None or interval <= 0:
        return []

    lower_bound = max(window.start, today)
    current = next_date

    while current < lower_bound:
        current = _add_workdays(current, interval)

    projected: list[date] = []
    while current <= window.end:
        projected.append(current)
        current = _add_workdays(current, interval)

    return projected


def _schedule_branch_name(
    schedule: MaintenancePreventiveScheduleORM,
) -> str:
    branch = getattr(schedule, "sucursal", None)
    return str(
        getattr(branch, "sucursal", None)
        or getattr(branch, "nombre", None)
        or "Sin sucursal"
    )


def _serialize_projection(
    schedule: MaintenancePreventiveScheduleORM,
    scheduled_date: date,
) -> dict:
    target_type = str(
        getattr(schedule, "target_type", None) or "EQUIPO"
    ).strip().upper()
    inventory = getattr(schedule, "inventario", None)
    building = getattr(schedule, "building_classification", None)

    if target_type == "EQUIPO":
        equipment_label = (
            getattr(inventory, "nombre", None)
            or "Sin equipo"
        )
        equipment_code = getattr(inventory, "codigo_interno", None)
    else:
        equipment_label = (
            getattr(building, "nombre", None)
            or "Edificio"
        )
        equipment_code = None

    return {
        "item_kind": "RECURRENCE_PROJECTION",
        "ticket_id": None,
        "schedule_id": int(schedule.id),
        "tipo_mantenimiento": "PREVENTIVO",
        "estado": "PREVISTO",
        "operational_status": "PREVISTO",
        "fecha_trabajo": scheduled_date.isoformat(),
        "sucursal_id": int(schedule.sucursal_id),
        "sucursal": _schedule_branch_name(schedule),
        "target_type": target_type,
        "clasificacion_id": schedule.building_classification_id,
        "inventario_id": schedule.inventario_id,
        "codigo_equipo": equipment_code,
        "equipo": equipment_label,
        "actividad": schedule.actividad,
        "problema_detectado": None,
        "necesita_refaccion": False,
        "descripcion_refaccion": None,
        "repeat_interval_workdays": int(
            schedule.repeat_interval_workdays
        ),
        "estimated_duration_minutes": getattr(
            schedule,
            "estimated_duration_minutes",
            None,
        ),
    }


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
        "item_kind": "TICKET",
        "ticket_id": int(ticket.id),
        "schedule_id": None,
        "tipo_mantenimiento": maintenance_type,
        "estado": ticket.estado,
        "operational_status": operational_status,
        "fecha_trabajo": work_date.isoformat() if work_date else None,
        "sucursal_id": (
            ticket.sucursal_id_destino or ticket.sucursal_id
        ),
        "sucursal": _branch_name(ticket),
        "target_type": (
            str(getattr(ticket, "maintenance_target_type", None) or "")
            .strip()
            .upper()
            or (
                "EQUIPO"
                if ticket.aparato_id is not None
                else "EDIFICIO"
                if ticket.clasificacion_id is not None
                else None
            )
        ),
        "clasificacion_id": ticket.clasificacion_id,
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
        "repeat_interval_workdays": None,
        "estimated_duration_minutes": getattr(
            ticket,
            "maintenance_estimated_minutes",
            None,
        ),
    }


def _build_workload(items: list[dict]) -> dict:
    by_date: dict[str, dict] = {}
    total_estimated = 0
    total_projected = 0
    total_unestimated = 0

    for item in items:
        if item.get("operational_status") == "PENDIENTE_VALIDACION":
            continue

        work_date = item.get("fecha_trabajo")
        if not work_date:
            continue

        day = by_date.setdefault(
            work_date,
            {
                "date": work_date,
                "estimated_minutes": 0,
                "capacity_minutes": DAILY_CAPACITY_MINUTES,
                "item_count": 0,
                "projected_count": 0,
                "unestimated_count": 0,
            },
        )
        day["item_count"] += 1

        if item.get("item_kind") == "RECURRENCE_PROJECTION":
            day["projected_count"] += 1

        raw_duration = item.get("estimated_duration_minutes")
        try:
            duration = int(raw_duration)
        except (TypeError, ValueError):
            duration = 0

        if duration <= 0:
            day["unestimated_count"] += 1
            total_unestimated += 1
            continue

        day["estimated_minutes"] += duration
        total_estimated += duration

        if item.get("item_kind") == "RECURRENCE_PROJECTION":
            total_projected += duration

    days = []
    for day in sorted(by_date.values(), key=lambda row: row["date"]):
        estimated = int(day["estimated_minutes"])
        capacity = int(day["capacity_minutes"])
        over_minutes = max(0, estimated - capacity)
        utilization = round((estimated / capacity) * 100, 1) if capacity else 0

        days.append(
            {
                **day,
                "utilization_percent": utilization,
                "over_capacity": over_minutes > 0,
                "over_minutes": over_minutes,
            }
        )

    return {
        "reference_daily_capacity_minutes": DAILY_CAPACITY_MINUTES,
        "estimated_minutes": total_estimated,
        "projected_minutes": total_projected,
        "unestimated_count": total_unestimated,
        "scheduled_days": len(days),
        "overloaded_days": sum(
            1 for day in days if day["over_capacity"]
        ),
        "days": days,
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

    schedules = (
        MaintenancePreventiveScheduleORM.query
        .filter(
            MaintenancePreventiveScheduleORM.active.is_(True),
            MaintenancePreventiveScheduleORM.responsable_user_id
            == int(user.id),
            MaintenancePreventiveScheduleORM.next_scheduled_date
            <= window.end,
        )
        .order_by(
            MaintenancePreventiveScheduleORM.next_scheduled_date.asc(),
            MaintenancePreventiveScheduleORM.id.asc(),
        )
        .all()
    )

    projected_items = [
        _serialize_projection(schedule, projected_date)
        for schedule in schedules
        for projected_date in _projection_dates(
            schedule,
            window,
            today,
        )
    ]

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
    ] + projected_items
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
        1 if row.get("item_kind") == "RECURRENCE_PROJECTION" else 0,
        row.get("ticket_id") or row.get("schedule_id") or 0,
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
            "projected": len(projected_items),
            "overdue": len(overdue),
            "pending_validation": len(pending_validation),
            "unscheduled": len(unscheduled),
        },
        "workload": _build_workload(week_items),
        "today_items": sorted(today_items, key=sort_key),
        "week_items": sorted(week_items, key=sort_key),
        "projected_items": sorted(projected_items, key=sort_key),
        "overdue": sorted(overdue, key=sort_key),
        "pending_validation": sorted(
            pending_validation,
            key=sort_key,
        ),
        "unscheduled": sorted(unscheduled, key=sort_key),
    }
