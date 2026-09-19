# backend/app/services/maintenance_weekly_dashboard_service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from dateutil import parser
from sqlalchemy import and_, or_
from zoneinfo import ZoneInfo

from app.models.maintenance_preventive import (
    MaintenanceCrewORM,
    MaintenancePersonnelORM,
)
from app.models.sucursal_model import Sucursal
from app.models.suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
)
from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.utils.pm_permissions import can_pm_configure, can_pm_view
from app.utils.sucursal_audience import (
    SUCURSAL_AUDIENCE_OPERATIONAL,
    apply_selectable_sucursal_catalog,
)


BUSINESS_TZ = ZoneInfo("America/Tijuana")
GLOBAL_DASHBOARD_ROLES = {
    "ADMIN",
    "ADMINISTRADOR",
    "SUPER_ADMIN",
    "MANTENIMIENTO",
    "LECTOR_GLOBAL",
}
TECHNICAL_BRANCH_IDS = {100, 1000}


class MaintenanceWeeklyDashboardError(ValueError):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class MaintenanceWeeklyDashboardAuthorizationError(
    MaintenanceWeeklyDashboardError
):
    status_code = 403


@dataclass(frozen=True)
class DashboardFilters:
    branch_ids: tuple[int, ...]
    region_id: int | None
    branch_id: int | None
    crew_id: int | None
    responsible_user_id: int | None
    responsible_usernames: tuple[str, ...] | None


@dataclass(frozen=True)
class WeekWindow:
    start: date
    end: date


def _role(user) -> str:
    return str(getattr(user, "rol", "") or "").strip().upper()


def _business_date(value: datetime | None) -> date | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)

    return value.astimezone(BUSINESS_TZ).date()


def _parse_date(value: str | None, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise MaintenanceWeeklyDashboardError(
            f"{field} debe tener formato YYYY-MM-DD."
        ) from exc


def _current_business_date() -> date:
    return datetime.now(BUSINESS_TZ).date()


def _sunday_for(reference: date) -> date:
    return reference - timedelta(
        days=(reference.weekday() + 1) % 7
    )


def _week_windows(
    reference: date,
    weeks: int,
) -> list[WeekWindow]:
    current_start = _sunday_for(reference)
    oldest_start = current_start - timedelta(
        days=7 * (weeks - 1)
    )

    return [
        WeekWindow(
            start=oldest_start + timedelta(days=7 * index),
            end=oldest_start + timedelta(days=7 * index + 6),
        )
        for index in range(weeks)
    ]


def _all_selectable_branches() -> list[Sucursal]:
    return (
        apply_selectable_sucursal_catalog(
            Sucursal.query,
            audience=SUCURSAL_AUDIENCE_OPERATIONAL,
        )
        .order_by(Sucursal.sucursal.asc())
        .all()
    )


def _assigned_branch_ids(user) -> set[int]:
    result: set[int] = set()

    for value in (getattr(user, "sucursales_ids", None) or []):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in TECHNICAL_BRANCH_IDS:
            result.add(parsed)

    try:
        primary = int(getattr(user, "sucursal_id", 0) or 0)
    except (TypeError, ValueError):
        primary = 0

    if primary > 0 and primary not in TECHNICAL_BRANCH_IDS:
        result.add(primary)

    return result


def _allowed_branch_ids(user) -> set[int]:
    if not user or not can_pm_view(user):
        raise MaintenanceWeeklyDashboardAuthorizationError(
            "No tienes permiso para consultar el panel de Mantenimiento."
        )

    selectable = {
        int(branch.sucursal_id)
        for branch in _all_selectable_branches()
    }

    if _role(user) in GLOBAL_DASHBOARD_ROLES:
        return selectable

    return selectable.intersection(
        _assigned_branch_ids(user)
    )


def _region_branch_ids(region_id: int) -> set[int]:
    rows = (
        SuiteSucursalRegionAssignmentORM.query
        .filter(
            SuiteSucursalRegionAssignmentORM.region_id == int(region_id),
            SuiteSucursalRegionAssignmentORM.is_current.is_(True),
        )
        .all()
    )
    return {
        int(row.sucursal_id)
        for row in rows
    }


def _personnel_rows_for_crew(
    crew_id: int,
) -> list[MaintenancePersonnelORM]:
    return (
        MaintenancePersonnelORM.query
        .filter(
            MaintenancePersonnelORM.crew_id == int(crew_id),
            MaintenancePersonnelORM.activo.is_(True),
        )
        .all()
    )


def _personnel_for_user(
    user_id: int,
) -> MaintenancePersonnelORM | None:
    return (
        MaintenancePersonnelORM.query
        .filter(
            MaintenancePersonnelORM.user_id == int(user_id),
            MaintenancePersonnelORM.activo.is_(True),
        )
        .first()
    )


def _resolve_filters(
    user,
    *,
    region_id: int | None = None,
    branch_id: int | None = None,
    crew_id: int | None = None,
    responsible_user_id: int | None = None,
) -> DashboardFilters:
    allowed = _allowed_branch_ids(user)
    scoped = set(allowed)

    if region_id is not None:
        region = SuiteRegionORM.query.filter_by(
            id=int(region_id),
            is_active=True,
        ).first()
        if region is None:
            raise MaintenanceWeeklyDashboardError(
                "La región indicada no existe o está inactiva."
            )
        scoped.intersection_update(
            _region_branch_ids(int(region_id))
        )

    if branch_id is not None:
        if int(branch_id) not in allowed:
            raise MaintenanceWeeklyDashboardAuthorizationError(
                "No tienes acceso a la sucursal indicada."
            )
        if int(branch_id) not in scoped:
            scoped.clear()
        else:
            scoped = {int(branch_id)}

    usernames: set[str] | None = None

    if crew_id is not None:
        crew = MaintenanceCrewORM.query.filter_by(
            id=int(crew_id),
            activo=True,
        ).first()
        if crew is None:
            raise MaintenanceWeeklyDashboardError(
                "La cuadrilla indicada no existe o está inactiva."
            )

        crew_personnel = _personnel_rows_for_crew(int(crew_id))
        usernames = {
            str(row.user.username).strip().casefold()
            for row in crew_personnel
            if row.user and str(row.user.username or "").strip()
        }

        if crew.region_id is not None:
            scoped.intersection_update(
                _region_branch_ids(int(crew.region_id))
            )

    if responsible_user_id is not None:
        personnel = _personnel_for_user(
            int(responsible_user_id)
        )
        if personnel is None or personnel.user is None:
            raise MaintenanceWeeklyDashboardError(
                "El responsable no está activo en el catálogo "
                "de Mantenimiento."
            )

        username = str(
            personnel.user.username or ""
        ).strip().casefold()

        if usernames is not None and username not in usernames:
            usernames = set()
        else:
            usernames = {username}

    return DashboardFilters(
        branch_ids=tuple(sorted(scoped)),
        region_id=int(region_id) if region_id is not None else None,
        branch_id=int(branch_id) if branch_id is not None else None,
        crew_id=int(crew_id) if crew_id is not None else None,
        responsible_user_id=(
            int(responsible_user_id)
            if responsible_user_id is not None
            else None
        ),
        responsible_usernames=(
            tuple(sorted(usernames))
            if usernames is not None
            else None
        ),
    )


def _ticket_scope_condition(branch_ids: tuple[int, ...]):
    ids = list(branch_ids)
    if not ids:
        return None

    return or_(
        Ticket.sucursal_id_destino.in_(ids),
        and_(
            Ticket.sucursal_id_destino.is_(None),
            Ticket.sucursal_id.in_(ids),
        ),
    )


def _base_ticket_query(
    filters: DashboardFilters,
):
    scope_condition = _ticket_scope_condition(
        filters.branch_ids
    )
    if scope_condition is None:
        return Ticket.query.filter(False)

    query = Ticket.query.filter(
        Ticket.departamento_id == 1,
        scope_condition,
    )

    if filters.responsible_usernames is not None:
        usernames = list(filters.responsible_usernames)
        if not usernames:
            return query.filter(False)

        query = query.filter(
            db_lower_assigned().in_(usernames)
        )

    return query


def db_lower_assigned():
    from sqlalchemy import func

    return func.lower(Ticket.asignado_a)


def _validated_date(ticket: Ticket) -> date | None:
    if (
        str(ticket.tipo_mantenimiento or "").strip().upper()
        == "PREVENTIVO"
    ):
        # En preventivos fecha_finalizado es ejecución del técnico;
        # el KPI oficial concluye únicamente con validación del gerente.
        return _business_date(ticket.fecha_validacion_cierre)

    return _business_date(
        ticket.fecha_validacion_cierre
        or ticket.fecha_finalizado
    )


def _preventive_original_date(
    ticket: Ticket,
) -> date | None:
    return _business_date(
        ticket.fecha_programada_original
        or ticket.fecha_programada_actual
    )


def _preventive_current_date(
    ticket: Ticket,
) -> date | None:
    return _business_date(ticket.fecha_programada_actual)


def _corrective_original_due(
    ticket: Ticket,
) -> date | None:
    return _business_date(
        ticket.fecha_compromiso_original
        or ticket.fecha_solucion
    )


def _corrective_current_due(
    ticket: Ticket,
) -> date | None:
    return _business_date(ticket.fecha_solucion)


def _history_datetime(value) -> datetime | None:
    if not value:
        return None

    try:
        parsed = parser.isoparse(str(value))
    except Exception:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _corrective_due_as_of(
    ticket: Ticket,
    as_of: date,
) -> date | None:
    original = _corrective_original_due(ticket)
    if original is None:
        return None

    latest_due = original
    latest_change: datetime | None = None

    for item in (ticket.historial_fechas or []):
        if not isinstance(item, dict):
            continue

        changed_at = _history_datetime(
            item.get("fechaCambio")
            or item.get("fecha_cambio")
        )
        due_at = _history_datetime(
            item.get("fecha")
            or item.get("fecha_solucion")
        )

        if changed_at is None or due_at is None:
            continue

        changed_business_date = _business_date(changed_at)
        if (
            changed_business_date is None
            or changed_business_date > as_of
        ):
            continue

        if latest_change is None or changed_at > latest_change:
            latest_change = changed_at
            latest_due = _business_date(due_at) or latest_due

    return latest_due


def _aging_bucket(days: int) -> str:
    normalized = max(1, int(days))

    if normalized <= 7:
        return "1_7"
    if normalized <= 14:
        return "8_14"
    if normalized <= 30:
        return "15_30"
    return "31_PLUS"


def _created_date(ticket: Ticket) -> date | None:
    return _business_date(ticket.fecha_creacion)


def _in_window(value: date | None, week: WeekWindow) -> bool:
    return (
        value is not None
        and week.start <= value <= week.end
    )


def _ids(rows: list[Ticket]) -> list[int]:
    return [int(row.id) for row in rows]


def _metric(
    rows: list[Ticket],
    *,
    denominator: int | None = None,
) -> dict:
    count = len(rows)
    result = {
        "count": count,
        "ticket_ids": _ids(rows),
    }

    if denominator is not None:
        result["percent"] = (
            round((count / denominator) * 100, 2)
            if denominator > 0
            else 0.0
        )

    return result


def _is_reprogrammed(
    original: date | None,
    current: date | None,
) -> bool:
    return (
        original is not None
        and current is not None
        and original != current
    )


def _ticket_was_reprogrammed(
    ticket: Ticket,
    original: date | None,
    current: date | None,
) -> bool:
    if _is_reprogrammed(original, current):
        return True

    if original is None:
        return False

    for item in (ticket.historial_fechas or []):
        if not isinstance(item, dict):
            continue

        event = str(
            item.get("evento")
            or item.get("tipo")
            or ""
        ).strip().lower()

        if event in {
            "reprogramacion_mantenimiento",
            "rechazo_cierre_gerente",
        }:
            return True

        historical_due = _history_datetime(
            item.get("fecha")
            or item.get("fecha_nueva")
            or item.get("fecha_solucion")
        )
        historical_date = _business_date(historical_due)

        if (
            historical_date is not None
            and historical_date != original
        ):
            return True

    return False


def _build_week_card(
    week: WeekWindow,
    preventives: list[Ticket],
    correctives: list[Ticket],
) -> dict:
    preventive_cohort = [
        ticket
        for ticket in preventives
        if _in_window(
            _preventive_original_date(ticket),
            week,
        )
    ]
    preventive_reprogrammed = [
        ticket
        for ticket in preventive_cohort
        if _ticket_was_reprogrammed(
            ticket,
            _preventive_original_date(ticket),
            _preventive_current_date(ticket),
        )
    ]
    preventive_on_time = [
        ticket
        for ticket in preventive_cohort
        if (
            ticket not in preventive_reprogrammed
            and _validated_date(ticket) is not None
            and _validated_date(ticket) <= week.end
        )
    ]
    preventive_eventually = [
        ticket
        for ticket in preventive_cohort
        if _validated_date(ticket) is not None
    ]
    preventive_missed = [
        ticket
        for ticket in preventive_cohort
        if (
            ticket not in preventive_on_time
            and ticket not in preventive_reprogrammed
        )
    ]
    preventive_pending_now = [
        ticket
        for ticket in preventive_cohort
        if _validated_date(ticket) is None
    ]

    corrective_due = [
        ticket
        for ticket in correctives
        if _in_window(
            _corrective_original_due(ticket),
            week,
        )
    ]
    corrective_reprogrammed = [
        ticket
        for ticket in corrective_due
        if _ticket_was_reprogrammed(
            ticket,
            _corrective_original_due(ticket),
            _corrective_current_due(ticket),
        )
    ]
    corrective_on_time = [
        ticket
        for ticket in corrective_due
        if (
            ticket not in corrective_reprogrammed
            and _validated_date(ticket) is not None
            and _corrective_original_due(ticket) is not None
            and _validated_date(ticket)
            <= _corrective_original_due(ticket)
        )
    ]
    corrective_missed = [
        ticket
        for ticket in corrective_due
        if (
            ticket not in corrective_on_time
            and ticket not in corrective_reprogrammed
        )
    ]
    corrective_pending_now = [
        ticket
        for ticket in corrective_due
        if _validated_date(ticket) is None
    ]
    corrective_demand = [
        ticket
        for ticket in correctives
        if _in_window(_created_date(ticket), week)
    ]
    corrective_demand_reactive = [
        ticket
        for ticket in corrective_demand
        if (
            str(ticket.origen_correctivo or "REACTIVO")
            .strip()
            .upper()
            == "REACTIVO"
        )
    ]
    corrective_demand_detected = [
        ticket
        for ticket in corrective_demand
        if (
            str(ticket.origen_correctivo or "")
            .strip()
            .upper()
            == "DETECTADO_EN_PREVENTIVO"
        )
    ]

    backlog_start = [
        ticket
        for ticket in correctives
        if (
            _created_date(ticket) is not None
            and _created_date(ticket) < week.start
            and (
                _validated_date(ticket) is None
                or _validated_date(ticket) >= week.start
            )
        )
    ]
    backlog_end = [
        ticket
        for ticket in correctives
        if (
            _created_date(ticket) is not None
            and _created_date(ticket) <= week.end
            and (
                _validated_date(ticket) is None
                or _validated_date(ticket) > week.end
            )
        )
    ]

    backlog_overdue_start = [
        ticket
        for ticket in backlog_start
        if (
            _corrective_due_as_of(ticket, week.start)
            is not None
            and _corrective_due_as_of(ticket, week.start)
            < week.start
        )
    ]
    backlog_overdue_end = [
        ticket
        for ticket in backlog_end
        if (
            _corrective_due_as_of(ticket, week.end)
            is not None
            and _corrective_due_as_of(ticket, week.end)
            <= week.end
        )
    ]

    preventive_denominator = len(preventive_cohort)
    corrective_denominator = len(corrective_due)

    return {
        "week_number": int(week.end.isocalendar().week),
        "week_start": week.start.isoformat(),
        "week_end": week.end.isoformat(),
        "preventive": {
            "programmed": _metric(preventive_cohort),
            "validated_on_time": _metric(
                preventive_on_time,
                denominator=preventive_denominator,
            ),
            "eventually_validated": _metric(
                preventive_eventually,
                denominator=preventive_denominator,
            ),
            "reprogrammed": _metric(
                preventive_reprogrammed,
                denominator=preventive_denominator,
            ),
            "missed": _metric(
                preventive_missed,
                denominator=preventive_denominator,
            ),
            "pending_now": _metric(
                preventive_pending_now,
                denominator=preventive_denominator,
            ),
            "strict_compliance_percent": (
                round(
                    len(preventive_on_time)
                    / preventive_denominator
                    * 100,
                    2,
                )
                if preventive_denominator
                else 0.0
            ),
            "current_progress_percent": (
                round(
                    len(preventive_eventually)
                    / preventive_denominator
                    * 100,
                    2,
                )
                if preventive_denominator
                else 0.0
            ),
        },
        "corrective": {
            "due": _metric(corrective_due),
            "validated_on_time": _metric(
                corrective_on_time,
                denominator=corrective_denominator,
            ),
            "reprogrammed": _metric(
                corrective_reprogrammed,
                denominator=corrective_denominator,
            ),
            "missed": _metric(
                corrective_missed,
                denominator=corrective_denominator,
            ),
            "pending_now": _metric(
                corrective_pending_now,
                denominator=corrective_denominator,
            ),
            "demand": _metric(corrective_demand),
            "demand_reactive": _metric(
                corrective_demand_reactive
            ),
            "demand_detected_preventive": _metric(
                corrective_demand_detected
            ),
            "fulfillment_percent": (
                round(
                    len(corrective_on_time)
                    / corrective_denominator
                    * 100,
                    2,
                )
                if corrective_denominator
                else 0.0
            ),
        },
        "backlog": {
            "start": _metric(backlog_start),
            "end": _metric(backlog_end),
            "delta": len(backlog_end) - len(backlog_start),
            "overdue_start": _metric(backlog_overdue_start),
            "overdue_end": _metric(backlog_overdue_end),
            "overdue_delta": (
                len(backlog_overdue_end)
                - len(backlog_overdue_start)
            ),
        },
    }


def _serialize_ticket_summary(ticket: Ticket) -> dict:
    branch = ticket.sucursal_destino or ticket.sucursal
    inventory = ticket.inventario

    return {
        "id": int(ticket.id),
        "tipo_mantenimiento": ticket.tipo_mantenimiento,
        "origen_correctivo": ticket.origen_correctivo,
        "estado": ticket.estado,
        "estado_cierre": ticket.estado_cierre,
        "descripcion": ticket.descripcion,
        "criticidad": ticket.criticidad,
        "asignado_a": ticket.asignado_a,
        "sucursal_id": (
            ticket.sucursal_id_destino
            or ticket.sucursal_id
        ),
        "sucursal": (
            getattr(branch, "sucursal", None)
            or getattr(branch, "nombre", None)
            or "Sin sucursal"
        ),
        "codigo_equipo": (
            getattr(inventory, "codigo_interno", None)
            if inventory is not None
            else None
        ),
        "equipo": (
            getattr(inventory, "nombre", None)
            or ticket.equipo
            or "Sin equipo"
        ),
        "fecha_creacion": (
            ticket.fecha_creacion.isoformat()
            if ticket.fecha_creacion
            else None
        ),
        "fecha_programada_original": (
            ticket.fecha_programada_original.isoformat()
            if ticket.fecha_programada_original
            else None
        ),
        "fecha_programada_actual": (
            ticket.fecha_programada_actual.isoformat()
            if ticket.fecha_programada_actual
            else None
        ),
        "fecha_compromiso_original": (
            ticket.fecha_compromiso_original.isoformat()
            if ticket.fecha_compromiso_original
            else None
        ),
        "fecha_solucion": (
            ticket.fecha_solucion.isoformat()
            if ticket.fecha_solucion
            else None
        ),
        "fecha_validacion_cierre": (
            ticket.fecha_validacion_cierre.isoformat()
            if ticket.fecha_validacion_cierre
            else None
        ),
        "ticket_preventivo_origen_id": (
            ticket.ticket_preventivo_origen_id
        ),
    }


def get_dashboard_context(user) -> dict:
    allowed = _allowed_branch_ids(user)

    branches = [
        branch
        for branch in _all_selectable_branches()
        if int(branch.sucursal_id) in allowed
    ]

    assignments = (
        SuiteSucursalRegionAssignmentORM.query
        .filter(
            SuiteSucursalRegionAssignmentORM.is_current.is_(True),
            SuiteSucursalRegionAssignmentORM.sucursal_id.in_(
                list(allowed)
            ) if allowed else False,
        )
        .all()
        if allowed
        else []
    )

    branch_region_map = {
        int(row.sucursal_id): int(row.region_id)
        for row in assignments
    }
    region_ids = set(branch_region_map.values())
    regions = (
        SuiteRegionORM.query
        .filter(
            SuiteRegionORM.id.in_(list(region_ids)),
            SuiteRegionORM.is_active.is_(True),
        )
        .order_by(SuiteRegionORM.region_label.asc())
        .all()
        if region_ids
        else []
    )

    crews = (
        MaintenanceCrewORM.query
        .filter(MaintenanceCrewORM.activo.is_(True))
        .order_by(MaintenanceCrewORM.nombre.asc())
        .all()
    )
    visible_crews = [
        crew
        for crew in crews
        if (
            crew.region_id is None
            or int(crew.region_id) in region_ids
        )
    ]

    personnel = (
        MaintenancePersonnelORM.query
        .filter(MaintenancePersonnelORM.activo.is_(True))
        .order_by(MaintenancePersonnelORM.id.asc())
        .all()
    )
    visible_personnel = [
        row
        for row in personnel
        if row.user is not None
        and (
            row.crew is None
            or row.crew.region_id is None
            or int(row.crew.region_id) in region_ids
        )
    ]

    return {
        "permissions": {
            "can_reprogram": bool(can_pm_configure(user)),
        },
        "sucursales": [
            {
                "id": int(branch.sucursal_id),
                "nombre": str(branch.sucursal),
                "region_id": branch_region_map.get(
                    int(branch.sucursal_id)
                ),
            }
            for branch in branches
        ],
        "regiones": [
            {
                "id": int(region.id),
                "key": str(region.region_key),
                "nombre": str(region.region_label),
            }
            for region in regions
        ],
        "cuadrillas": [
            {
                "id": int(crew.id),
                "nombre": str(crew.nombre),
                "region_id": crew.region_id,
            }
            for crew in visible_crews
        ],
        "responsables": [
            {
                "user_id": int(row.user.id),
                "username": str(row.user.username),
                "crew_id": row.crew_id,
            }
            for row in visible_personnel
        ],
    }


def build_weekly_dashboard(
    user,
    *,
    weeks: int = 8,
    reference_date: str | None = None,
    region_id: int | None = None,
    branch_id: int | None = None,
    crew_id: int | None = None,
    responsible_user_id: int | None = None,
) -> dict:
    try:
        weeks = int(weeks)
    except (TypeError, ValueError) as exc:
        raise MaintenanceWeeklyDashboardError(
            "weeks inválido."
        ) from exc

    if weeks < 1 or weeks > 12:
        raise MaintenanceWeeklyDashboardError(
            "weeks debe estar entre 1 y 12."
        )

    reference = (
        _parse_date(reference_date, "reference_date")
        or _current_business_date()
    )
    windows = _week_windows(reference, weeks)
    filters = _resolve_filters(
        user,
        region_id=region_id,
        branch_id=branch_id,
        crew_id=crew_id,
        responsible_user_id=responsible_user_id,
    )

    base_query = _base_ticket_query(filters)

    preventives = (
        base_query
        .filter(Ticket.tipo_mantenimiento == "PREVENTIVO")
        .all()
    )
    correctives = (
        base_query
        .filter(Ticket.tipo_mantenimiento == "CORRECTIVO")
        .all()
    )

    cards = [
        _build_week_card(
            week,
            preventives,
            correctives,
        )
        for week in windows
    ]

    return {
        "reference_date": reference.isoformat(),
        "weeks": cards,
        "filters": {
            "region_id": filters.region_id,
            "branch_id": filters.branch_id,
            "crew_id": filters.crew_id,
            "responsible_user_id": filters.responsible_user_id,
            "branch_ids": list(filters.branch_ids),
        },
        "context": get_dashboard_context(user),
    }


VALID_DRILLDOWN_METRICS = {
    "preventive.programmed",
    "preventive.validated_on_time",
    "preventive.eventually_validated",
    "preventive.reprogrammed",
    "preventive.missed",
    "preventive.pending_now",
    "corrective.due",
    "corrective.validated_on_time",
    "corrective.reprogrammed",
    "corrective.missed",
    "corrective.pending_now",
    "corrective.demand",
    "corrective.demand_reactive",
    "corrective.demand_detected_preventive",
    "backlog.start",
    "backlog.end",
    "backlog.overdue_start",
    "backlog.overdue_end",
}


def build_dashboard_drilldown(
    user,
    *,
    week_start: str,
    metric: str,
    region_id: int | None = None,
    branch_id: int | None = None,
    crew_id: int | None = None,
    responsible_user_id: int | None = None,
) -> dict:
    if metric not in VALID_DRILLDOWN_METRICS:
        raise MaintenanceWeeklyDashboardError(
            "Métrica de drill-down inválida."
        )

    start = _parse_date(week_start, "week_start")
    if start is None:
        raise MaintenanceWeeklyDashboardError(
            "week_start es obligatorio."
        )

    if _sunday_for(start) != start:
        raise MaintenanceWeeklyDashboardError(
            "week_start debe ser domingo."
        )

    filters = _resolve_filters(
        user,
        region_id=region_id,
        branch_id=branch_id,
        crew_id=crew_id,
        responsible_user_id=responsible_user_id,
    )
    base_query = _base_ticket_query(filters)

    preventives = (
        base_query
        .filter(Ticket.tipo_mantenimiento == "PREVENTIVO")
        .all()
    )
    correctives = (
        base_query
        .filter(Ticket.tipo_mantenimiento == "CORRECTIVO")
        .all()
    )

    week = WeekWindow(
        start=start,
        end=start + timedelta(days=6),
    )
    card = _build_week_card(
        week,
        preventives,
        correctives,
    )

    root, leaf = metric.split(".", 1)
    metric_payload = card[root][leaf]
    ticket_ids = metric_payload.get("ticket_ids", [])

    tickets = (
        base_query
        .filter(Ticket.id.in_(ticket_ids))
        .order_by(Ticket.id.desc())
        .all()
        if ticket_ids
        else []
    )

    as_of = (
        week.start
        if metric == "backlog.overdue_start"
        else week.end
    )
    aging = None
    ticket_rows = []

    for ticket in tickets:
        row = _serialize_ticket_summary(ticket)

        if metric in {
            "backlog.overdue_start",
            "backlog.overdue_end",
        }:
            due_as_of = _corrective_due_as_of(
                ticket,
                as_of,
            )
            overdue_days = (
                max(1, (as_of - due_as_of).days)
                if due_as_of is not None
                else None
            )
            row["commitment_as_of"] = (
                due_as_of.isoformat()
                if due_as_of is not None
                else None
            )
            row["overdue_days"] = overdue_days
            row["aging_bucket"] = (
                _aging_bucket(overdue_days)
                if overdue_days is not None
                else None
            )

        ticket_rows.append(row)

    if metric in {
        "backlog.overdue_start",
        "backlog.overdue_end",
    }:
        aging = {
            "1_7": 0,
            "8_14": 0,
            "15_30": 0,
            "31_PLUS": 0,
        }
        for row in ticket_rows:
            bucket = row.get("aging_bucket")
            if bucket in aging:
                aging[bucket] += 1

    return {
        "metric": metric,
        "week_start": week.start.isoformat(),
        "week_end": week.end.isoformat(),
        "count": len(tickets),
        "aging": aging,
        "tickets": ticket_rows,
    }
