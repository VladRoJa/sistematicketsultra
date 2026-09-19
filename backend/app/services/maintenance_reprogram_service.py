# backend/app/services/maintenance_reprogram_service.py

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models.maintenance_preventive import (
    MaintenanceReprogramReasonORM,
)
from app.models.ticket_model import Ticket
from app.utils.pm_permissions import can_pm_configure


BUSINESS_TZ = ZoneInfo("America/Tijuana")
GLOBAL_CONFIG_ROLES = {
    "ADMIN",
    "ADMINISTRADOR",
    "SUPER_ADMIN",
    "MANTENIMIENTO",
}
TECHNICAL_BRANCH_IDS = {100, 1000}


class MaintenanceReprogramError(ValueError):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class MaintenanceReprogramAuthorizationError(MaintenanceReprogramError):
    status_code = 403


class MaintenanceReprogramNotFoundError(MaintenanceReprogramError):
    status_code = 404


class MaintenanceReprogramStateError(MaintenanceReprogramError):
    status_code = 409


def _role(user) -> str:
    return str(getattr(user, "rol", "") or "").strip().upper()


def _clean(value) -> str:
    return str(value or "").strip()


def _assert_can_configure(user) -> None:
    if not user or not can_pm_configure(user):
        raise MaintenanceReprogramAuthorizationError(
            "No tienes permiso para reprogramar mantenimiento."
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


def _ticket_branch_id(ticket: Ticket) -> int | None:
    raw = ticket.sucursal_id_destino or ticket.sucursal_id
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _assert_ticket_scope(user, ticket: Ticket) -> None:
    if _role(user) in GLOBAL_CONFIG_ROLES:
        return

    branch_id = _ticket_branch_id(ticket)
    if branch_id is None or branch_id not in _assigned_branch_ids(user):
        raise MaintenanceReprogramAuthorizationError(
            "No tienes acceso a la sucursal de este ticket."
        )


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return _normalize_utc(value).astimezone(BUSINESS_TZ).date()

    if isinstance(value, date):
        return value

    raw = _clean(value)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise MaintenanceReprogramError(
            "nueva_fecha debe tener formato YYYY-MM-DD."
        ) from exc


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date_to_utc(value: date) -> datetime:
    local = datetime.combine(
        value,
        time(hour=7),
        tzinfo=BUSINESS_TZ,
    )
    return local.astimezone(timezone.utc)


def _serialize_reason(reason: MaintenanceReprogramReasonORM) -> dict:
    return {
        "id": int(reason.id),
        "key": str(reason.key),
        "nombre": str(reason.nombre),
        "requiere_comentario": bool(reason.requiere_comentario),
        "activo": bool(reason.activo),
        "orden": int(reason.orden or 0),
    }


def listar_motivos_reprogramacion(
    user,
    *,
    include_inactive: bool = False,
) -> list[dict]:
    _assert_can_configure(user)

    query = MaintenanceReprogramReasonORM.query

    if not include_inactive:
        query = query.filter(
            MaintenanceReprogramReasonORM.activo.is_(True)
        )

    rows = (
        query
        .order_by(
            MaintenanceReprogramReasonORM.orden.asc(),
            MaintenanceReprogramReasonORM.nombre.asc(),
        )
        .all()
    )

    return [_serialize_reason(row) for row in rows]


def crear_motivo_reprogramacion(
    user,
    payload: dict,
) -> MaintenanceReprogramReasonORM:
    _assert_can_configure(user)

    key = _clean((payload or {}).get("key")).upper().replace(" ", "_")
    name = _clean((payload or {}).get("nombre"))

    if not key or not name:
        raise MaintenanceReprogramError(
            "key y nombre son obligatorios."
        )

    existing = MaintenanceReprogramReasonORM.query.filter_by(
        key=key
    ).first()
    if existing is not None:
        raise MaintenanceReprogramStateError(
            "Ya existe un motivo con esa key."
        )

    try:
        order = int((payload or {}).get("orden") or 0)
    except (TypeError, ValueError) as exc:
        raise MaintenanceReprogramError("orden inválido.") from exc

    row = MaintenanceReprogramReasonORM(
        key=key,
        nombre=name,
        requiere_comentario=bool(
            (payload or {}).get("requiere_comentario", False)
        ),
        activo=True,
        orden=order,
    )
    db.session.add(row)
    db.session.flush()
    return row


def actualizar_motivo_reprogramacion(
    user,
    reason_id: int,
    payload: dict,
) -> MaintenanceReprogramReasonORM:
    _assert_can_configure(user)

    row = db.session.get(
        MaintenanceReprogramReasonORM,
        int(reason_id),
    )
    if row is None:
        raise MaintenanceReprogramNotFoundError(
            "Motivo de reprogramación no encontrado."
        )

    if "nombre" in payload:
        name = _clean(payload.get("nombre"))
        if not name:
            raise MaintenanceReprogramError(
                "nombre es obligatorio."
            )
        row.nombre = name

    if "requiere_comentario" in payload:
        row.requiere_comentario = bool(
            payload.get("requiere_comentario")
        )

    if "activo" in payload:
        row.activo = bool(payload.get("activo"))

    if "orden" in payload:
        try:
            row.orden = int(payload.get("orden"))
        except (TypeError, ValueError) as exc:
            raise MaintenanceReprogramError(
                "orden inválido."
            ) from exc

    db.session.flush()
    return row


def serializar_motivo_reprogramacion(
    reason: MaintenanceReprogramReasonORM,
) -> dict:
    return _serialize_reason(reason)


def reprogramar_ticket_mantenimiento(
    user,
    ticket_id: int,
    payload: dict,
) -> Ticket:
    _assert_can_configure(user)

    ticket = db.session.get(Ticket, int(ticket_id))
    if ticket is None:
        raise MaintenanceReprogramNotFoundError(
            "Ticket no encontrado."
        )

    if int(ticket.departamento_id or 0) != 1:
        raise MaintenanceReprogramStateError(
            "El ticket no pertenece a Mantenimiento."
        )

    maintenance_type = str(
        ticket.tipo_mantenimiento or ""
    ).strip().upper()

    if maintenance_type not in {"PREVENTIVO", "CORRECTIVO"}:
        raise MaintenanceReprogramStateError(
            "El ticket no tiene semántica de mantenimiento válida."
        )

    state = str(ticket.estado or "").strip().lower()
    if state not in {"abierto", "en progreso"}:
        raise MaintenanceReprogramStateError(
            "Solo se pueden reprogramar tickets abiertos o en progreso."
        )

    _assert_ticket_scope(user, ticket)

    try:
        reason_id = int((payload or {}).get("reason_id"))
    except (TypeError, ValueError) as exc:
        raise MaintenanceReprogramError(
            "reason_id es obligatorio."
        ) from exc

    reason = db.session.get(
        MaintenanceReprogramReasonORM,
        reason_id,
    )
    if reason is None or not bool(reason.activo):
        raise MaintenanceReprogramError(
            "El motivo no existe o está inactivo."
        )

    comment = _clean((payload or {}).get("comentario"))
    if reason.requiere_comentario and not comment:
        raise MaintenanceReprogramError(
            "El comentario es obligatorio para este motivo."
        )

    new_date = _parse_date((payload or {}).get("nueva_fecha"))
    new_due_utc = _date_to_utc(new_date)

    if maintenance_type == "PREVENTIVO":
        previous_due = (
            ticket.fecha_programada_actual
            or ticket.fecha_programada_original
        )
        if previous_due is None:
            raise MaintenanceReprogramStateError(
                "El preventivo no tiene fecha programada vigente."
            )

        if ticket.fecha_programada_original is None:
            ticket.fecha_programada_original = previous_due

        if (
            _normalize_utc(previous_due).astimezone(BUSINESS_TZ).date()
            == new_date
        ):
            raise MaintenanceReprogramStateError(
                "La nueva fecha es igual a la programación vigente."
            )

        ticket.fecha_programada_actual = new_due_utc
    else:
        previous_due = ticket.fecha_solucion
        if previous_due is None:
            raise MaintenanceReprogramStateError(
                "El correctivo no tiene compromiso vigente."
            )

        if (
            _normalize_utc(previous_due).astimezone(BUSINESS_TZ).date()
            == new_date
        ):
            raise MaintenanceReprogramStateError(
                "La nueva fecha es igual al compromiso vigente."
            )

        ticket.asignar_fecha_compromiso(new_due_utc)

    now = datetime.now(timezone.utc)
    history = list(ticket.historial_fechas or [])
    history.append(
        {
            "evento": "reprogramacion_mantenimiento",
            "tipo_mantenimiento": maintenance_type,
            "fecha_anterior": _normalize_utc(
                previous_due
            ).isoformat(),
            "fecha": new_due_utc.isoformat(),
            "fecha_nueva": new_due_utc.isoformat(),
            "reason_id": int(reason.id),
            "motivo_key": str(reason.key),
            "motivo": str(reason.nombre),
            "comentario": comment or None,
            "cambiadoPor": str(
                getattr(user, "username", "") or ""
            ).strip(),
            "fechaCambio": now.isoformat(),
            "origen": "tickets_preventive_v1",
        }
    )
    history.sort(
        key=lambda item: str(
            item.get("fechaCambio")
            or item.get("fecha_cambio")
            or ""
        ),
        reverse=True,
    )
    ticket.historial_fechas = history
    flag_modified(ticket, "historial_fechas")

    db.session.flush()
    return ticket
