# backend/app/services/maintenance_execution_service.py

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from app.extensions import db
from app.models.maintenance_checklist import (
    MaintenanceChecklistTemplateORM,
)
from app.models.pm_bitacora import PmBitacoraORM
from app.models.ticket_model import Ticket
from app.models.ticket_attachment import TicketAttachmentORM
from app.services.maintenance_my_program_service import (
    MaintenanceMyProgramAuthorizationError,
    require_my_program_access,
)


BUSINESS_TZ = ZoneInfo("America/Tijuana")
MAINTENANCE_DEPARTMENT_ID = 1
CHECK_VALUES = {"OK", "ATENCION", "NO_APLICA"}
FOUND_STATES = {
    "BUENO": "OK",
    "REQUIERE_ATENCION": "OBS",
    "FUERA_SERVICIO": "FALLA",
}


class MaintenanceExecutionError(ValueError):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class MaintenanceExecutionAuthorizationError(MaintenanceExecutionError):
    status_code = 403


class MaintenanceExecutionNotFoundError(MaintenanceExecutionError):
    status_code = 404


class MaintenanceExecutionStateError(MaintenanceExecutionError):
    status_code = 409


def _normalize(value) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _owned_ticket(user, ticket_id: int) -> Ticket:
    try:
        require_my_program_access(user)
    except MaintenanceMyProgramAuthorizationError as exc:
        raise MaintenanceExecutionAuthorizationError(str(exc)) from exc

    username = str(getattr(user, "username", "") or "").strip()
    ticket = (
        Ticket.query
        .filter(
            Ticket.id == int(ticket_id),
            Ticket.departamento_id == MAINTENANCE_DEPARTMENT_ID,
            func.lower(Ticket.asignado_a) == username.casefold(),
        )
        .first()
    )

    if ticket is None:
        raise MaintenanceExecutionNotFoundError(
            "Trabajo no encontrado en tu programa."
        )

    return ticket


def _require_preventive_active(ticket: Ticket) -> None:
    if _normalize(ticket.tipo_mantenimiento) != "PREVENTIVO":
        raise MaintenanceExecutionStateError(
            "Este flujo de bitácora solo aplica a preventivos."
        )

    state = str(ticket.estado or "").strip().lower()
    if state not in {"abierto", "en progreso"}:
        raise MaintenanceExecutionStateError(
            "El preventivo ya no está disponible para ejecución."
        )


def _family_id(ticket: Ticket) -> int | None:
    if ticket.familia_equipo_id:
        return int(ticket.familia_equipo_id)

    inventory = ticket.inventario
    family_id = getattr(inventory, "familia_equipo_id", None)
    return int(family_id) if family_id else None


def resolve_checklist(ticket: Ticket) -> MaintenanceChecklistTemplateORM | None:
    family_id = _family_id(ticket)
    if family_id is None:
        return None

    activity_key = _normalize(ticket.descripcion)

    templates = (
        MaintenanceChecklistTemplateORM.query
        .filter(
            MaintenanceChecklistTemplateORM.familia_equipo_id == family_id,
            MaintenanceChecklistTemplateORM.activo.is_(True),
        )
        .order_by(MaintenanceChecklistTemplateORM.id.asc())
        .all()
    )

    exact = next(
        (
            template
            for template in templates
            if _normalize(template.actividad_key) == activity_key
            and template.actividad_key
        ),
        None,
    )
    if exact is not None:
        return exact

    return next(
        (
            template
            for template in templates
            if not str(template.actividad_key or "").strip()
        ),
        None,
    )


def serialize_checklist(template: MaintenanceChecklistTemplateORM | None) -> dict | None:
    if template is None:
        return None

    return {
        "id": int(template.id),
        "template_key": str(template.template_key),
        "nombre": str(template.nombre),
        "familia_equipo_id": int(template.familia_equipo_id),
        "actividad_key": template.actividad_key,
        "items": [
            {
                "id": int(item.id),
                "item_key": str(item.item_key),
                "etiqueta": str(item.etiqueta),
                "orden": int(item.orden or 0),
                "requerido": bool(item.requerido),
            }
            for item in template.items
            if bool(item.activo)
        ],
    }


def _serialize_bitacora(bitacora: PmBitacoraORM) -> dict:
    return {
        "id": int(bitacora.id),
        "ticket_id": bitacora.ticket_id,
        "fecha": bitacora.fecha.isoformat(),
        "resultado": bitacora.resultado,
        "estado_encontrado": bitacora.estado_encontrado,
        "notas": bitacora.notas,
        "checks": bitacora.checks or {},
        "hallazgo_detectado": bool(bitacora.hallazgo_detectado),
        "hallazgo_descripcion": bitacora.hallazgo_descripcion,
        "created_by_user_id": bitacora.created_by_user_id,
        "created_at": (
            bitacora.created_at.isoformat()
            if bitacora.created_at
            else None
        ),
    }


def get_work_detail(user, ticket_id: int) -> dict:
    ticket = _owned_ticket(user, ticket_id)
    _require_preventive_active(ticket)

    bitacoras = (
        PmBitacoraORM.query
        .filter(PmBitacoraORM.ticket_id == ticket.id)
        .order_by(PmBitacoraORM.created_at.desc(), PmBitacoraORM.id.desc())
        .all()
    )

    inventory = ticket.inventario
    branch = ticket.sucursal_destino or ticket.sucursal

    has_evidence = (
        TicketAttachmentORM.query
        .filter(
            TicketAttachmentORM.ticket_id == ticket.id,
            TicketAttachmentORM.deleted_at.is_(None),
        )
        .first()
        is not None
    )

    return {
        "ticket": {
            "id": int(ticket.id),
            "estado": ticket.estado,
            "tipo_mantenimiento": ticket.tipo_mantenimiento,
            "fecha_programada_actual": (
                ticket.fecha_programada_actual.isoformat()
                if ticket.fecha_programada_actual
                else None
            ),
            "sucursal_id": (
                ticket.sucursal_id_destino or ticket.sucursal_id
            ),
            "sucursal": str(
                getattr(branch, "sucursal", None)
                or getattr(branch, "nombre", None)
                or "Sin sucursal"
            ),
            "inventario_id": ticket.aparato_id,
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
            "actividad": ticket.descripcion,
        },
        "checklist": serialize_checklist(resolve_checklist(ticket)),
        "has_evidence": has_evidence,
        "bitacoras": [
            _serialize_bitacora(bitacora)
            for bitacora in bitacoras
        ],
    }


def _validated_checks(ticket: Ticket, payload_checks) -> dict:
    template = resolve_checklist(ticket)

    if template is None:
        if payload_checks not in (None, {}, []):
            raise MaintenanceExecutionError(
                "Este preventivo no tiene checklist configurado."
            )
        return {}

    if not isinstance(payload_checks, dict):
        raise MaintenanceExecutionError(
            "checks debe ser un objeto."
        )

    active_items = [
        item for item in template.items if bool(item.activo)
    ]
    active_keys = {str(item.item_key): item for item in active_items}

    result: dict[str, str] = {}

    for key, raw_value in payload_checks.items():
        key_text = str(key)
        if key_text not in active_keys:
            raise MaintenanceExecutionError(
                f"El check {key_text} no pertenece a la plantilla vigente."
            )

        value = _normalize(raw_value)
        if value not in CHECK_VALUES:
            raise MaintenanceExecutionError(
                "Cada check debe ser OK, ATENCION o NO_APLICA."
            )
        result[key_text] = value

    missing = [
        str(item.item_key)
        for item in active_items
        if bool(item.requerido)
        and str(item.item_key) not in result
    ]
    if missing:
        raise MaintenanceExecutionError(
            "Faltan checks obligatorios: " + ", ".join(missing)
        )

    return result


def _create_derived_corrective(
    *,
    preventive: Ticket,
    user,
    description: str,
    criticidad: int,
) -> Ticket:
    corrective = Ticket.create_ticket(
        descripcion=description,
        username=str(user.username),
        sucursal_id=int(user.sucursal_id),
        sucursal_id_destino=int(
            preventive.sucursal_id_destino or preventive.sucursal_id
        ),
        departamento_id=MAINTENANCE_DEPARTMENT_ID,
        criticidad=criticidad,
        clasificacion_id=None,
        aparato_id=preventive.aparato_id,
        problema_detectado=description,
        necesita_refaccion=False,
        descripcion_refaccion=None,
        ubicacion=preventive.ubicacion,
        equipo=preventive.equipo,
        estado="abierto",
        requiere_aprobacion=False,
        tipo_mantenimiento="CORRECTIVO",
        origen_correctivo="DETECTADO_EN_PREVENTIVO",
        ticket_preventivo_origen_id=preventive.id,
        commit=False,
    )
    corrective.familia_equipo_id = preventive.familia_equipo_id
    return corrective


def create_preventive_bitacora(
    user,
    ticket_id: int,
    payload: dict,
) -> dict:
    ticket = _owned_ticket(user, ticket_id)
    _require_preventive_active(ticket)

    if not isinstance(payload, dict):
        raise MaintenanceExecutionError(
            "El cuerpo de la bitácora es inválido."
        )

    found_state = _normalize(payload.get("estado_encontrado"))
    if found_state not in FOUND_STATES:
        raise MaintenanceExecutionError(
            "estado_encontrado debe ser BUENO, "
            "REQUIERE_ATENCION o FUERA_SERVICIO."
        )

    notes = str(payload.get("notas") or "").strip()
    if not notes:
        raise MaintenanceExecutionError(
            "Describe el trabajo realizado en notas."
        )

    checks = _validated_checks(ticket, payload.get("checks") or {})

    hallazgo = bool(payload.get("hallazgo_detectado", False))
    hallazgo_description = str(
        payload.get("hallazgo_descripcion") or ""
    ).strip()

    if hallazgo and not hallazgo_description:
        raise MaintenanceExecutionError(
            "Describe el hallazgo detectado."
        )

    branch_id = int(ticket.sucursal_id_destino or ticket.sucursal_id)
    if ticket.aparato_id is None:
        raise MaintenanceExecutionStateError(
            "El preventivo no tiene equipo de Inventario asociado."
        )

    bitacora = PmBitacoraORM(
        ticket_id=int(ticket.id),
        inventario_id=int(ticket.aparato_id),
        sucursal_id=branch_id,
        created_by_user_id=int(user.id),
        fecha=datetime.now(BUSINESS_TZ).date(),
        resultado=FOUND_STATES[found_state],
        tipo_mantenimiento="PREVENTIVO",
        notas=notes,
        estado_encontrado=found_state,
        hallazgo_detectado=hallazgo,
        hallazgo_descripcion=hallazgo_description or None,
        checks=checks,
    )
    db.session.add(bitacora)
    db.session.flush()

    corrective = None
    if hallazgo and bool(payload.get("generar_correctivo", False)):
        try:
            criticidad = int(payload.get("criticidad_correctivo") or 2)
        except (TypeError, ValueError) as exc:
            raise MaintenanceExecutionError(
                "criticidad_correctivo inválida."
            ) from exc

        if criticidad < 1 or criticidad > 5:
            raise MaintenanceExecutionError(
                "criticidad_correctivo debe estar entre 1 y 5."
            )

        corrective = _create_derived_corrective(
            preventive=ticket,
            user=user,
            description=hallazgo_description,
            criticidad=criticidad,
        )
        db.session.flush()

    if str(ticket.estado or "").strip().lower() == "abierto":
        ticket.estado = "en progreso"
        if ticket.fecha_en_progreso is None:
            ticket.fecha_en_progreso = datetime.now(timezone.utc)

    return {
        "bitacora": bitacora,
        "corrective": corrective,
    }


def complete_preventive(user, ticket_id: int) -> Ticket:
    ticket = _owned_ticket(user, ticket_id)
    _require_preventive_active(ticket)

    latest = (
        PmBitacoraORM.query
        .filter(
            PmBitacoraORM.ticket_id == ticket.id,
            PmBitacoraORM.created_by_user_id == int(user.id),
        )
        .order_by(PmBitacoraORM.created_at.desc(), PmBitacoraORM.id.desc())
        .first()
    )
    if latest is None:
        raise MaintenanceExecutionStateError(
            "Debes guardar una bitácora antes de marcar realizado."
        )

    now = datetime.now(timezone.utc)
    previous_state = ticket.estado
    previous_close_state = ticket.estado_cierre

    ticket.estado = "por_validar"
    ticket.estado_cierre = "pendiente_creador"
    ticket.fecha_finalizado = now
    ticket.motivo_rechazo_cierre = None

    ticket._agregar_evento_historial_cierre(
        evento="preventivo_realizado",
        actor_username=str(user.username),
        motivo=f"Bitácora PM #{latest.id}",
        estado_anterior=previous_state,
        estado_nuevo=ticket.estado,
        estado_cierre_anterior=previous_close_state,
        estado_cierre_nuevo=ticket.estado_cierre,
    )

    return ticket
