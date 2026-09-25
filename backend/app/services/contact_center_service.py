from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case as sql_case, func, or_, select

from app.extensions import db
from app.models.contact_center import (
    ContactCenterAppointmentORM,
    ContactCenterAppointmentResultEventORM,
    ContactCenterCaseORM,
    ContactCenterContactLinkORM,
    ContactCenterContactMergeEventORM,
    ContactCenterContactORM,
    ContactCenterInteractionORM,
)
from app.models.marketing import (
    MarketingIventasContactORM,
    MarketingIventasSyncRunORM,
)
from app.models.sucursal_model import Sucursal, SucursalOperationalStatus
from app.models.user_model import UserORM
from app.models.warehouse import (
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
)
from app.services.marketing_leads_detail_service import (
    build_marketing_lead_contacts_statement,
)
from app.services.marketing_phone import normalize_phone
from app.services.marketing_sales_funnel_service import (
    _is_valid_status,
    _normalize_text,
    _parse_row_date,
)
from app.utils.contact_center_access import has_contact_center_operator_access


BUSINESS_TZ = ZoneInfo("America/Tijuana")
CASE_SOURCES = frozenset({"CRM", "MESSAGE", "REACTIVATION", "CAMPAIGN", "MANUAL"})
INTERACTION_OUTCOMES = frozenset({
    "NO_ANSWER",
    "CALL_BACK",
    "INTERESTED",
    "APPOINTMENT",
    "NOT_INTERESTED",
    "WRONG_NUMBER",
    "DO_NOT_CONTACT",
    "NOTE",
})
APPOINTMENT_OUTCOMES = frozenset({
    "ATTENDED_PURCHASE_REPORTED",
    "ATTENDED_NO_PURCHASE",
    "NO_SHOW",
    "CANCELLED",
})
CLOSED_CASE_OUTCOMES = frozenset({
    "NOT_INTERESTED",
    "WRONG_NUMBER",
    "DO_NOT_CONTACT",
})

MEMBERSHIP_PURCHASE_TERMS = (
    "MEMBRESIA",
    "MENSUAL",
    "MENSUALIDAD",
    "INSCRIPCION",
    "DOMICILIADO",
    "RECURRENTE",
    "CONVENIO",
    "TRIMESTRAL",
    "TRIMESTRE",
    "SEMESTRAL",
    "SEMESTRE",
    "ANUALIDAD",
    "PRIMER PAGO",
    "CUENTA NUEVA",
    "NO FORZOSO",
    "PLAN FAMILIAR",
)


class ContactCenterValidationError(ValueError):
    pass


class ContactCenterNotFoundError(LookupError):
    pass


class ContactCenterDuplicateError(ContactCenterValidationError):
    def __init__(self, candidates: list[dict[str, Any]]):
        super().__init__("Se encontraron posibles contactos duplicados.")
        self.candidates = candidates


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_datetime(value: object, field_name: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ContactCenterValidationError(f"{field_name} es obligatorio.")

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContactCenterValidationError(
            f"{field_name} debe ser una fecha/hora ISO válida."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BUSINESS_TZ)

    return parsed.astimezone(timezone.utc)


def _clean_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _branch_payload(branch: Sucursal | None) -> dict[str, Any] | None:
    if branch is None:
        return None
    return {
        "id": int(branch.sucursal_id),
        "name": str(branch.sucursal),
    }


def _user_payload(user: UserORM | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": int(user.id),
        "username": str(user.username),
        "role": str(user.rol or ""),
    }


def serialize_contact(contact: ContactCenterContactORM) -> dict[str, Any]:
    return {
        "id": int(contact.id),
        "display_name": contact.display_name,
        "primary_phone_raw": contact.primary_phone_raw,
        "phone_mx10": contact.phone_mx10,
        "email": contact.email,
        "preferred_sucursal": _branch_payload(contact.preferred_sucursal),
        "is_active": bool(contact.is_active),
        "merged_into_contact_id": (
            int(contact.merged_into_contact_id)
            if contact.merged_into_contact_id is not None
            else None
        ),
        "created_at": _iso(contact.created_at),
        "updated_at": _iso(contact.updated_at),
    }


def serialize_case(case: ContactCenterCaseORM) -> dict[str, Any]:
    return {
        "id": int(case.id),
        "contact_id": int(case.contact_id),
        "source_type": case.source_type,
        "source_ref": case.source_ref,
        "sucursal": _branch_payload(case.sucursal),
        "assigned_user": _user_payload(case.assigned_user),
        "status": case.status,
        "next_action_at": _iso(case.next_action_at),
        "opened_at": _iso(case.opened_at),
        "closed_at": _iso(case.closed_at),
        "created_at": _iso(case.created_at),
        "updated_at": _iso(case.updated_at),
    }


def serialize_interaction(row: ContactCenterInteractionORM) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "case_id": int(row.case_id),
        "contact_id": int(row.contact_id),
        "interaction_type": row.interaction_type,
        "outcome": row.outcome,
        "comment": row.comment,
        "next_action_at": _iso(row.next_action_at),
        "created_by_user": _user_payload(row.created_by_user),
        "created_at": _iso(row.created_at),
    }


def serialize_appointment(row: ContactCenterAppointmentORM) -> dict[str, Any]:
    now = _now_utc()
    is_closure_pending = (
        row.status == "SCHEDULED"
        and row.outcome is None
        and row.scheduled_at < now
    )
    return {
        "id": int(row.id),
        "case_id": int(row.case_id),
        "contact_id": int(row.contact_id),
        "sucursal": _branch_payload(row.sucursal),
        "scheduled_at": _iso(row.scheduled_at),
        "timezone": row.timezone,
        "status": row.status,
        "outcome": row.outcome,
        "notes": row.notes,
        "closure_pending": is_closure_pending,
        "closed_at": _iso(row.closed_at),
        "rescheduled_to_appointment_id": (
            int(row.rescheduled_to_appointment_id)
            if row.rescheduled_to_appointment_id is not None
            else None
        ),
        "purchase_reported": bool(row.purchase_reported),
        "purchase_reported_at": _iso(row.purchase_reported_at),
        "purchase_verification_status": row.purchase_verification_status,
        "venta_total_snapshot_id": row.venta_total_snapshot_id,
        "venta_total_snapshot_row_id": row.venta_total_snapshot_row_id,
        "verified_purchase_at": _iso(row.verified_purchase_at),
        "verified_amount": (
            float(row.verified_amount)
            if row.verified_amount is not None
            else None
        ),
        "verified_tariff": row.verified_tariff,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def list_branches(
    allowed_branch_ids: tuple[int, ...] | None = None,
) -> list[dict[str, Any]]:
    query = Sucursal.query.filter(
        Sucursal.operational_status == SucursalOperationalStatus.ACTIVA,
        Sucursal.is_demo.is_(False),
    )

    if allowed_branch_ids is not None:
        if not allowed_branch_ids:
            return []
        query = query.filter(
            Sucursal.sucursal_id.in_(allowed_branch_ids)
        )

    rows = (
        query
        .order_by(
            Sucursal.orden_apertura.asc().nullslast(),
            Sucursal.sucursal.asc(),
        )
        .all()
    )
    return [_branch_payload(row) for row in rows if row is not None]


def list_agents() -> list[dict[str, Any]]:
    rows = UserORM.query.order_by(UserORM.username.asc()).all()
    return [
        _user_payload(row)
        for row in rows
        if has_contact_center_operator_access(row)
    ]


def find_duplicate_contacts(
    *,
    phone: object = None,
    email: object = None,
    exclude_contact_id: int | None = None,
) -> list[dict[str, Any]]:
    normalized_phone = normalize_phone(phone)
    normalized_email = _clean_text(email)
    filters = []

    if normalized_phone:
        filters.append(ContactCenterContactORM.phone_mx10 == normalized_phone)
    if normalized_email:
        filters.append(
            func.lower(ContactCenterContactORM.email)
            == normalized_email.lower()
        )

    if not filters:
        return []

    query = ContactCenterContactORM.query.filter(
        ContactCenterContactORM.is_active.is_(True),
        ContactCenterContactORM.merged_into_contact_id.is_(None),
        or_(*filters),
    )
    if exclude_contact_id is not None:
        query = query.filter(ContactCenterContactORM.id != exclude_contact_id)

    return [
        serialize_contact(row)
        for row in query.order_by(ContactCenterContactORM.updated_at.desc()).limit(20).all()
    ]


def create_contact_with_case(
    payload: dict[str, Any],
    actor: UserORM,
    *,
    forced_assigned_user_id: int | None = None,
    allowed_branch_ids: tuple[int, ...] | None = None,
) -> tuple[ContactCenterContactORM, ContactCenterCaseORM]:
    raw_phone = _clean_text(payload.get("phone"))
    if raw_phone is None:
        raise ContactCenterValidationError("El teléfono es obligatorio.")

    phone_mx10 = normalize_phone(raw_phone)
    if phone_mx10 is None:
        raise ContactCenterValidationError(
            "El teléfono debe poder resolverse a 10 dígitos de México."
        )

    duplicates = find_duplicate_contacts(
        phone=raw_phone,
        email=payload.get("email"),
    )
    if duplicates:
        raise ContactCenterDuplicateError(duplicates)

    source_type = str(payload.get("source_type") or "MANUAL").strip().upper()
    if source_type not in CASE_SOURCES:
        raise ContactCenterValidationError("Origen de caso inválido.")

    branch_id = payload.get("sucursal_id")
    branch = None
    if branch_id not in (None, ""):
        try:
            branch_id = int(branch_id)
        except (TypeError, ValueError) as exc:
            raise ContactCenterValidationError("Sucursal inválida.") from exc
        branch = Sucursal.query.filter_by(sucursal_id=branch_id).first()
        if branch is None:
            raise ContactCenterValidationError("Sucursal no encontrada.")

    if allowed_branch_ids is not None:
        if branch is None:
            raise ContactCenterValidationError(
                "Selecciona una sucursal autorizada."
            )
        if int(branch_id) not in set(allowed_branch_ids):
            raise ContactCenterValidationError(
                "Sólo puedes crear contactos para tus sucursales autorizadas."
            )

    contact = ContactCenterContactORM(
        display_name=_clean_text(payload.get("name")),
        primary_phone_raw=raw_phone,
        phone_mx10=phone_mx10,
        email=_clean_text(payload.get("email")),
        preferred_sucursal_id=branch_id if branch is not None else None,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    db.session.add(contact)
    db.session.flush()

    if forced_assigned_user_id is not None:
        try:
            assigned_user_id = int(forced_assigned_user_id)
        except (TypeError, ValueError) as exc:
            raise ContactCenterValidationError(
                "Agente asignado inválido."
            ) from exc

        if assigned_user_id != int(actor.id):
            raise ContactCenterValidationError(
                "La asignación forzada debe corresponder al usuario actual."
            )
        assigned_user = actor
    else:
        assigned_user_id = payload.get("assigned_user_id") or actor.id
        try:
            assigned_user_id = int(assigned_user_id)
        except (TypeError, ValueError) as exc:
            raise ContactCenterValidationError(
                "Agente asignado inválido."
            ) from exc

        assigned_user = UserORM.get_by_id(assigned_user_id)
        if not has_contact_center_operator_access(assigned_user):
            raise ContactCenterValidationError(
                "El agente seleccionado no tiene acceso operativo a Contact Center."
            )

    case = ContactCenterCaseORM(
        contact_id=contact.id,
        source_type=source_type,
        source_ref=_clean_text(payload.get("source_ref")),
        sucursal_id=branch_id if branch is not None else None,
        assigned_user_id=assigned_user_id,
        status="NEW",
        created_by_user_id=actor.id,
    )
    db.session.add(case)
    db.session.flush()

    comment = _clean_text(payload.get("comment"))
    if comment:
        db.session.add(
            ContactCenterInteractionORM(
                case_id=case.id,
                contact_id=contact.id,
                interaction_type="NOTE",
                outcome="NOTE",
                comment=comment,
                created_by_user_id=actor.id,
            )
        )

    return contact, case


def list_contacts(
    *,
    actor: UserORM,
    is_supervisor: bool,
    include_all_assignees: bool = False,
    allowed_branch_ids: tuple[int, ...] | None = None,
    status: str | None = None,
    source_type: str | None = None,
    query_text: str | None = None,
) -> list[dict[str, Any]]:
    cases_query = ContactCenterCaseORM.query

    if allowed_branch_ids is not None:
        if not allowed_branch_ids:
            return []
        cases_query = cases_query.filter(
            ContactCenterCaseORM.sucursal_id.in_(allowed_branch_ids)
        )

    if not is_supervisor and not include_all_assignees:
        cases_query = cases_query.filter(
            ContactCenterCaseORM.assigned_user_id == actor.id
        )

    normalized_status = str(status or "").strip().upper()
    if normalized_status:
        cases_query = cases_query.filter(
            ContactCenterCaseORM.status == normalized_status
        )

    normalized_source = str(source_type or "").strip().upper()
    if normalized_source:
        cases_query = cases_query.filter(
            ContactCenterCaseORM.source_type == normalized_source
        )

    rows = (
        cases_query
        .join(
            ContactCenterContactORM,
            ContactCenterContactORM.id == ContactCenterCaseORM.contact_id,
        )
        .filter(
            ContactCenterContactORM.is_active.is_(True),
            ContactCenterContactORM.merged_into_contact_id.is_(None),
        )
        .order_by(
            sql_case(
                (ContactCenterCaseORM.status == "CLOSED", 1),
                else_=0,
            ).asc(),
            ContactCenterCaseORM.next_action_at.asc().nullslast(),
            ContactCenterCaseORM.updated_at.desc(),
        )
        .all()
    )

    needle = str(query_text or "").strip().casefold()
    result = []
    seen_contact_ids: set[int] = set()

    for case_row in rows:
        contact = case_row.contact
        contact_id = int(contact.id)
        if contact_id in seen_contact_ids:
            continue

        if needle:
            haystack = " ".join([
                str(contact.display_name or ""),
                str(contact.phone_mx10 or ""),
                str(contact.primary_phone_raw or ""),
                str(contact.email or ""),
            ]).casefold()
            if needle not in haystack:
                continue

        seen_contact_ids.add(contact_id)
        payload = serialize_contact(contact)
        payload["case"] = serialize_case(case_row)
        result.append(payload)

    return result


def get_contact_detail(contact_id: int) -> dict[str, Any]:
    contact = ContactCenterContactORM.query.get(contact_id)
    if contact is None or contact.merged_into_contact_id is not None:
        raise ContactCenterNotFoundError("Contacto no encontrado.")

    cases = (
        ContactCenterCaseORM.query
        .filter_by(contact_id=contact.id)
        .order_by(ContactCenterCaseORM.created_at.desc())
        .all()
    )
    interactions = (
        ContactCenterInteractionORM.query
        .filter_by(contact_id=contact.id)
        .order_by(ContactCenterInteractionORM.created_at.desc())
        .all()
    )
    appointments = (
        ContactCenterAppointmentORM.query
        .filter_by(contact_id=contact.id)
        .order_by(ContactCenterAppointmentORM.scheduled_at.desc())
        .all()
    )
    links = (
        ContactCenterContactLinkORM.query
        .filter_by(contact_id=contact.id)
        .order_by(ContactCenterContactLinkORM.created_at.asc())
        .all()
    )

    payload = serialize_contact(contact)
    payload.update({
        "cases": [serialize_case(row) for row in cases],
        "interactions": [serialize_interaction(row) for row in interactions],
        "appointments": [serialize_appointment(row) for row in appointments],
        "links": [
            {
                "id": int(row.id),
                "source_type": row.source_type,
                "source_key": row.source_key,
                "source_row_id": row.source_row_id,
                "source_metadata": row.source_metadata_json,
            }
            for row in links
        ],
    })
    return payload


def assign_case(
    case_id: int,
    assigned_user_id: int,
    actor: UserORM,
    *,
    is_supervisor: bool,
) -> ContactCenterCaseORM:
    if not is_supervisor:
        raise ContactCenterValidationError(
            "Sólo el supervisor puede reasignar casos."
        )

    case = ContactCenterCaseORM.query.get(case_id)
    if case is None:
        raise ContactCenterNotFoundError("Caso no encontrado.")
    if case.status == "CLOSED":
        raise ContactCenterValidationError(
            "No se puede reasignar un caso cerrado."
        )

    assigned_user = UserORM.get_by_id(assigned_user_id)
    if not has_contact_center_operator_access(assigned_user):
        raise ContactCenterValidationError(
            "El usuario seleccionado no tiene acceso operativo a Contact Center."
        )

    case.assigned_user_id = assigned_user_id
    case.updated_at = _now_utc()

    db.session.add(
        ContactCenterInteractionORM(
            case_id=case.id,
            contact_id=case.contact_id,
            interaction_type="SYSTEM",
            outcome="NOTE",
            comment=(
                f"Caso asignado a {assigned_user.username} "
                f"por {actor.username}."
            ),
            created_by_user_id=actor.id,
        )
    )
    db.session.flush()
    return case


def add_interaction(
    case_id: int,
    payload: dict[str, Any],
    actor: UserORM,
    *,
    is_supervisor: bool,
) -> ContactCenterInteractionORM:
    case = ContactCenterCaseORM.query.get(case_id)
    if case is None:
        raise ContactCenterNotFoundError("Caso no encontrado.")
    if not is_supervisor and case.assigned_user_id != actor.id:
        raise ContactCenterValidationError(
            "El caso está asignado a otro agente."
        )
    if case.status == "CLOSED":
        raise ContactCenterValidationError("El caso ya está cerrado.")

    outcome = str(payload.get("outcome") or "").strip().upper()
    if outcome not in INTERACTION_OUTCOMES:
        raise ContactCenterValidationError("Resultado de interacción inválido.")
    if outcome == "APPOINTMENT":
        raise ContactCenterValidationError(
            "Las citas deben registrarse desde la acción Agendar cita."
        )

    next_action_at = None
    if outcome == "CALL_BACK":
        next_action_at = _parse_datetime(
            payload.get("next_action_at"),
            "next_action_at",
        )

    interaction_type = str(
        payload.get("interaction_type") or "CALL"
    ).strip().upper()
    if interaction_type not in {"CALL", "MESSAGE", "NOTE"}:
        raise ContactCenterValidationError("Tipo de interacción inválido.")

    row = ContactCenterInteractionORM(
        case_id=case.id,
        contact_id=case.contact_id,
        interaction_type=interaction_type,
        outcome=outcome,
        comment=_clean_text(payload.get("comment")),
        next_action_at=next_action_at,
        created_by_user_id=actor.id,
    )
    db.session.add(row)

    if outcome in CLOSED_CASE_OUTCOMES:
        case.status = "CLOSED"
        case.closed_at = _now_utc()
        case.closed_by_user_id = actor.id
        case.next_action_at = None
    elif outcome == "CALL_BACK":
        case.status = "FOLLOW_UP"
        case.next_action_at = next_action_at
    else:
        case.status = "IN_PROGRESS"
        case.next_action_at = None

    case.updated_at = _now_utc()
    db.session.flush()
    return row


def create_appointment(
    case_id: int,
    payload: dict[str, Any],
    actor: UserORM,
    *,
    is_supervisor: bool,
) -> ContactCenterAppointmentORM:
    case = (
        ContactCenterCaseORM.query
        .filter(ContactCenterCaseORM.id == case_id)
        .with_for_update()
        .first()
    )
    if case is None:
        raise ContactCenterNotFoundError("Caso no encontrado.")
    if not is_supervisor and case.assigned_user_id != actor.id:
        raise ContactCenterValidationError(
            "El caso está asignado a otro agente."
        )
    if case.status == "CLOSED":
        raise ContactCenterValidationError("El caso ya está cerrado.")

    existing_appointment = (
        ContactCenterAppointmentORM.query
        .filter(
            ContactCenterAppointmentORM.case_id == case.id,
            ContactCenterAppointmentORM.status == "SCHEDULED",
        )
        .order_by(ContactCenterAppointmentORM.scheduled_at.desc())
        .first()
    )
    if existing_appointment is not None:
        raise ContactCenterValidationError(
            "Este caso ya tiene una cita programada. "
            "Usa Reagendar para cambiar la fecha o sucursal."
        )

    try:
        branch_id = int(payload.get("sucursal_id"))
    except (TypeError, ValueError) as exc:
        raise ContactCenterValidationError("Sucursal inválida.") from exc

    branch = Sucursal.query.filter_by(sucursal_id=branch_id).first()
    if branch is None:
        raise ContactCenterValidationError("Sucursal no encontrada.")

    scheduled_at = _parse_datetime(payload.get("scheduled_at"), "scheduled_at")
    if scheduled_at <= _now_utc():
        raise ContactCenterValidationError(
            "La cita debe programarse en una fecha futura."
        )

    appointment = ContactCenterAppointmentORM(
        case_id=case.id,
        contact_id=case.contact_id,
        sucursal_id=branch_id,
        scheduled_at=scheduled_at,
        timezone="America/Tijuana",
        notes=_clean_text(payload.get("notes")),
        created_by_user_id=actor.id,
    )
    db.session.add(appointment)

    db.session.add(
        ContactCenterInteractionORM(
            case_id=case.id,
            contact_id=case.contact_id,
            interaction_type="CALL",
            outcome="APPOINTMENT",
            comment=_clean_text(payload.get("notes")),
            created_by_user_id=actor.id,
        )
    )

    case.status = "APPOINTMENT"
    case.sucursal_id = branch_id
    case.next_action_at = scheduled_at
    case.updated_at = _now_utc()
    db.session.flush()
    return appointment


def _clear_appointment_purchase_state(
    appointment: ContactCenterAppointmentORM,
) -> None:
    appointment.purchase_reported = False
    appointment.purchase_reported_at = None
    appointment.purchase_reported_by_user_id = None
    appointment.purchase_verification_status = "NOT_REPORTED"
    appointment.venta_total_snapshot_id = None
    appointment.venta_total_snapshot_row_id = None
    appointment.verified_purchase_at = None
    appointment.verified_amount = None
    appointment.verified_tariff = None


def _apply_appointment_result(
    appointment: ContactCenterAppointmentORM,
    *,
    outcome: str,
    changed_by_user_id: int | None,
    notes: str | None = None,
    now: datetime | None = None,
) -> None:
    if outcome not in APPOINTMENT_OUTCOMES:
        raise ContactCenterValidationError("Resultado de cita inválido.")

    changed_at = now or _now_utc()

    appointment.outcome = outcome
    appointment.status = "CANCELLED" if outcome == "CANCELLED" else "CLOSED"
    appointment.closed_by_user_id = changed_by_user_id
    appointment.closed_at = changed_at
    appointment.updated_at = changed_at

    if notes:
        appointment.notes = notes

    if outcome == "ATTENDED_PURCHASE_REPORTED":
        appointment.purchase_reported = True
        appointment.purchase_reported_at = changed_at
        appointment.purchase_reported_by_user_id = changed_by_user_id
        appointment.purchase_verification_status = "REPORTED_PENDING"
        appointment.venta_total_snapshot_id = None
        appointment.venta_total_snapshot_row_id = None
        appointment.verified_purchase_at = None
        appointment.verified_amount = None
        appointment.verified_tariff = None
    else:
        _clear_appointment_purchase_state(appointment)

    case = appointment.case
    case.next_action_at = None
    case.updated_at = changed_at

    if outcome == "NO_SHOW":
        case.status = "IN_PROGRESS"
        case.closed_at = None
        case.closed_by_user_id = None
    else:
        case.status = "CLOSED"
        case.closed_at = changed_at
        case.closed_by_user_id = changed_by_user_id


def _record_appointment_result_event(
    appointment: ContactCenterAppointmentORM,
    *,
    previous_status: str | None,
    previous_outcome: str | None,
    previous_case_status: str | None,
    source: str,
    changed_by_user_id: int | None = None,
    venta_total_snapshot_id: int | None = None,
    venta_total_snapshot_row_id: int | None = None,
    reason: str | None = None,
) -> None:
    db.session.add(
        ContactCenterAppointmentResultEventORM(
            appointment_id=appointment.id,
            previous_status=previous_status,
            new_status=appointment.status,
            previous_outcome=previous_outcome,
            new_outcome=appointment.outcome,
            previous_case_status=previous_case_status,
            new_case_status=appointment.case.status,
            source=source,
            changed_by_user_id=changed_by_user_id,
            venta_total_snapshot_id=venta_total_snapshot_id,
            venta_total_snapshot_row_id=venta_total_snapshot_row_id,
            reason=_clean_text(reason),
        )
    )


def close_appointment(
    appointment_id: int,
    payload: dict[str, Any],
    actor: UserORM,
) -> ContactCenterAppointmentORM:
    appointment = ContactCenterAppointmentORM.query.get(appointment_id)
    if appointment is None:
        raise ContactCenterNotFoundError("Cita no encontrada.")
    if appointment.status != "SCHEDULED":
        raise ContactCenterValidationError(
            "La cita ya fue cerrada, cancelada o reagendada."
        )

    outcome = str(payload.get("outcome") or "").strip().upper()
    notes = _clean_text(payload.get("notes"))

    _apply_appointment_result(
        appointment,
        outcome=outcome,
        changed_by_user_id=int(actor.id),
        notes=notes,
    )
    db.session.flush()
    return appointment


def correct_appointment_result(
    appointment_id: int,
    payload: dict[str, Any],
    actor: UserORM,
) -> ContactCenterAppointmentORM:
    appointment = (
        ContactCenterAppointmentORM.query
        .filter_by(id=appointment_id)
        .with_for_update()
        .one_or_none()
    )
    if appointment is None:
        raise ContactCenterNotFoundError("Cita no encontrada.")

    if appointment.status not in {"CLOSED", "CANCELLED"}:
        raise ContactCenterValidationError(
            "Sólo se puede corregir el resultado de una cita ya cerrada."
        )

    outcome = str(payload.get("outcome") or "").strip().upper()
    if outcome not in APPOINTMENT_OUTCOMES:
        raise ContactCenterValidationError("Resultado de cita inválido.")

    if outcome == appointment.outcome:
        raise ContactCenterValidationError(
            "Selecciona un resultado distinto al actual."
        )

    if (
        appointment.purchase_verification_status == "VERIFIED"
        and outcome != "ATTENDED_PURCHASE_REPORTED"
    ):
        raise ContactCenterValidationError(
            "La cita ya tiene una compra validada por Venta Total."
        )

    previous_status = appointment.status
    previous_outcome = appointment.outcome
    previous_case_status = appointment.case.status
    reason = _clean_text(payload.get("notes"))

    _apply_appointment_result(
        appointment,
        outcome=outcome,
        changed_by_user_id=int(actor.id),
        notes=reason,
    )

    _record_appointment_result_event(
        appointment,
        previous_status=previous_status,
        previous_outcome=previous_outcome,
        previous_case_status=previous_case_status,
        source="MANUAL_CORRECTION",
        changed_by_user_id=int(actor.id),
        reason=reason,
    )

    db.session.add(
        ContactCenterInteractionORM(
            case_id=appointment.case_id,
            contact_id=appointment.contact_id,
            interaction_type="SYSTEM",
            outcome="NOTE",
            comment=(
                "Resultado de cita corregido: "
                f"{previous_outcome or 'SIN_RESULTADO'} -> {outcome}."
            ),
            created_by_user_id=actor.id,
        )
    )

    db.session.flush()
    return appointment

def reschedule_appointment(
    appointment_id: int,
    payload: dict[str, Any],
    actor: UserORM,
) -> ContactCenterAppointmentORM:
    current = ContactCenterAppointmentORM.query.get(appointment_id)
    if current is None:
        raise ContactCenterNotFoundError("Cita no encontrada.")
    if current.status != "SCHEDULED":
        raise ContactCenterValidationError("La cita ya no puede reagendarse.")

    scheduled_at = _parse_datetime(payload.get("scheduled_at"), "scheduled_at")
    if scheduled_at <= _now_utc():
        raise ContactCenterValidationError(
            "La nueva cita debe programarse en una fecha futura."
        )

    branch_id = payload.get("sucursal_id") or current.sucursal_id
    try:
        branch_id = int(branch_id)
    except (TypeError, ValueError) as exc:
        raise ContactCenterValidationError("Sucursal inválida.") from exc
    if Sucursal.query.filter_by(sucursal_id=branch_id).first() is None:
        raise ContactCenterValidationError("Sucursal no encontrada.")

    replacement = ContactCenterAppointmentORM(
        case_id=current.case_id,
        contact_id=current.contact_id,
        sucursal_id=branch_id,
        scheduled_at=scheduled_at,
        timezone="America/Tijuana",
        notes=_clean_text(payload.get("notes")) or current.notes,
        created_by_user_id=actor.id,
    )
    db.session.add(replacement)
    db.session.flush()

    now = _now_utc()
    current.status = "RESCHEDULED"
    current.outcome = "RESCHEDULED"
    current.closed_by_user_id = actor.id
    current.closed_at = now
    current.rescheduled_to_appointment_id = replacement.id
    current.updated_at = now

    current.case.status = "APPOINTMENT"
    current.case.sucursal_id = branch_id
    current.case.next_action_at = scheduled_at
    current.case.updated_at = now

    db.session.add(
        ContactCenterInteractionORM(
            case_id=current.case_id,
            contact_id=current.contact_id,
            interaction_type="NOTE",
            outcome="NOTE",
            comment="Cita reagendada.",
            next_action_at=scheduled_at,
            created_by_user_id=actor.id,
        )
    )
    return replacement


def list_appointments(
    *,
    actor: UserORM,
    is_supervisor: bool,
    include_all_assignees: bool = False,
    allowed_branch_ids: tuple[int, ...] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    query = ContactCenterAppointmentORM.query

    if allowed_branch_ids is not None:
        if not allowed_branch_ids:
            return []
        query = query.filter(
            ContactCenterAppointmentORM.sucursal_id.in_(allowed_branch_ids)
        )
    elif not is_supervisor and not include_all_assignees:
        query = (
            query
            .join(
                ContactCenterCaseORM,
                ContactCenterCaseORM.id == ContactCenterAppointmentORM.case_id,
            )
            .filter(ContactCenterCaseORM.assigned_user_id == actor.id)
        )
    if date_from is not None:
        start = datetime.combine(
            date_from,
            datetime.min.time(),
            tzinfo=BUSINESS_TZ,
        ).astimezone(timezone.utc)
        query = query.filter(ContactCenterAppointmentORM.scheduled_at >= start)
    if date_to is not None:
        end = datetime.combine(
            date_to,
            datetime.max.time(),
            tzinfo=BUSINESS_TZ,
        ).astimezone(timezone.utc)
        query = query.filter(ContactCenterAppointmentORM.scheduled_at <= end)

    rows = query.order_by(ContactCenterAppointmentORM.scheduled_at.desc()).all()
    result = []
    for row in rows:
        payload = serialize_appointment(row)
        payload["contact"] = serialize_contact(row.contact)
        payload["case"] = serialize_case(row.case)
        result.append(payload)
    return result


def _contact_center_crm_link_state() -> tuple[
    dict[str, int],
    dict[str, tuple[int, ...]],
    dict[int, int | None],
]:
    existing_links = {
        str(row.source_key): int(row.contact_id)
        for row in ContactCenterContactLinkORM.query
        .filter(ContactCenterContactLinkORM.source_type == "IVENTAS_CONTACT")
        .all()
    }

    active_contacts = (
        ContactCenterContactORM.query
        .filter(
            ContactCenterContactORM.is_active.is_(True),
            ContactCenterContactORM.merged_into_contact_id.is_(None),
            ContactCenterContactORM.phone_mx10.isnot(None),
        )
        .all()
    )

    contact_ids_by_phone: dict[str, list[int]] = defaultdict(list)
    active_contact_ids: list[int] = []
    for contact in active_contacts:
        contact_id = int(contact.id)
        phone = str(contact.phone_mx10 or "").strip()
        if not phone:
            continue
        contact_ids_by_phone[phone].append(contact_id)
        active_contact_ids.append(contact_id)

    phone_contact_ids = {
        phone: tuple(sorted(contact_ids))
        for phone, contact_ids in contact_ids_by_phone.items()
    }

    active_case_owner_ids: dict[int, int | None] = {}
    if active_contact_ids:
        rows = (
            db.session.query(
                ContactCenterCaseORM.contact_id,
                ContactCenterCaseORM.assigned_user_id,
            )
            .filter(
                ContactCenterCaseORM.contact_id.in_(
                    tuple(sorted(set(active_contact_ids)))
                ),
                ContactCenterCaseORM.status != "CLOSED",
            )
            .order_by(ContactCenterCaseORM.updated_at.desc())
            .all()
        )
        for contact_id, assigned_user_id in rows:
            active_case_owner_ids.setdefault(
                int(contact_id),
                (
                    int(assigned_user_id)
                    if assigned_user_id is not None
                    else None
                ),
            )

    return (
        existing_links,
        phone_contact_ids,
        active_case_owner_ids,
    )


def _serialize_crm_candidate(
    row: Any,
    *,
    branch_names: dict[int, str],
    existing_links: dict[str, int],
    phone_contact_ids: dict[str, tuple[int, ...]],
    active_case_owner_ids: dict[int, int | None],
) -> dict[str, Any]:
    branch_id = int(row["sucursal_id"])
    source_key = f"{branch_id}:{str(row['contact_id'])}"
    source_link_contact_id = existing_links.get(source_key)

    phone = normalize_phone(
        row.get("phone_mx10")
        or row.get("phone_digits")
    ) or ""
    phone_matches = phone_contact_ids.get(phone, tuple())

    phone_match_ambiguous = (
        source_link_contact_id is None
        and len(phone_matches) > 1
    )
    resolved_contact_id = source_link_contact_id
    matched_by_phone = False

    if resolved_contact_id is None and len(phone_matches) == 1:
        resolved_contact_id = int(phone_matches[0])
        matched_by_phone = True

    return {
        "contact_row_id": int(row["contact_row_id"]),
        "source_key": source_key,
        "sucursal_id": branch_id,
        "sucursal": branch_names.get(branch_id),
        "contact_id": str(row["contact_id"]),
        "name": _clean_text(row.get("name")),
        "phone": _clean_text(
            row.get("phone_mx10") or row.get("phone_digits")
        ),
        "first_message_at_local": _iso(row.get("first_message_at_local")),
        "channel_name": _clean_text(row.get("channel_name")),
        "channel_platform": _clean_text(row.get("channel_platform")),
        "already_in_contact_center": resolved_contact_id is not None,
        "contact_center_contact_id": resolved_contact_id,
        "crm_linked": source_link_contact_id is not None,
        "matched_by_phone": matched_by_phone,
        "phone_match_ambiguous": phone_match_ambiguous,
        "has_active_case": (
            resolved_contact_id in active_case_owner_ids
            if resolved_contact_id is not None
            else False
        ),
        "active_case_assigned_user_id": (
            active_case_owner_ids.get(resolved_contact_id)
            if resolved_contact_id is not None
            else None
        ),
    }


def search_crm_candidates_by_phone(
    phone: object,
    *,
    allowed_branch_ids: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    normalized_phone = normalize_phone(phone)
    if not normalized_phone or len(normalized_phone) != 10:
        raise ContactCenterValidationError(
            "Ingresa un teléfono mexicano válido de 10 dígitos."
        )

    run_branch_query = (
        db.session.query(
            MarketingIventasSyncRunORM.id.label("sync_run_id"),
            MarketingIventasSyncRunORM.date_to,
            MarketingIventasContactORM.sucursal_id,
        )
        .join(
            MarketingIventasContactORM,
            MarketingIventasContactORM.sync_run_id
            == MarketingIventasSyncRunORM.id,
        )
        .filter(
            MarketingIventasSyncRunORM.is_canonical.is_(True),
            MarketingIventasSyncRunORM.status == "COMPLETED",
            MarketingIventasContactORM.phone_mx10 == normalized_phone,
        )
    )

    if allowed_branch_ids is not None:
        if not allowed_branch_ids:
            return {
                "period_key": "HISTORICO",
                "sync_run_id": None,
                "rows": [],
            }
        run_branch_query = run_branch_query.filter(
            MarketingIventasContactORM.sucursal_id.in_(allowed_branch_ids)
        )

    run_branch_rows = (
        run_branch_query
        .distinct()
        .order_by(
            MarketingIventasSyncRunORM.date_to.desc(),
            MarketingIventasSyncRunORM.id.desc(),
        )
        .all()
    )

    if not run_branch_rows:
        return {
            "period_key": "HISTORICO",
            "sync_run_id": None,
            "rows": [],
        }

    branches_by_run: dict[int, set[int]] = defaultdict(set)
    ordered_run_ids: list[int] = []
    seen_run_ids: set[int] = set()
    all_branch_ids: set[int] = set()

    for item in run_branch_rows:
        run_id = int(item.sync_run_id)
        branch_id = int(item.sucursal_id)
        branches_by_run[run_id].add(branch_id)
        all_branch_ids.add(branch_id)
        if run_id not in seen_run_ids:
            ordered_run_ids.append(run_id)
            seen_run_ids.add(run_id)

    branch_names = {
        int(branch.sucursal_id): str(branch.sucursal)
        for branch in Sucursal.query
        .filter(Sucursal.sucursal_id.in_(tuple(sorted(all_branch_ids))))
        .all()
    }
    (
        existing_links,
        phone_contact_ids,
        active_case_owner_ids,
    ) = _contact_center_crm_link_state()

    result: list[dict[str, Any]] = []
    seen_source_keys: set[str] = set()

    for run_id in ordered_run_ids:
        statement = build_marketing_lead_contacts_statement(
            iventas_sync_run_id=run_id,
            branch_ids=tuple(sorted(branches_by_run[run_id])),
        ).where(
            MarketingIventasContactORM.phone_mx10 == normalized_phone
        )
        rows = db.session.execute(statement).mappings().all()

        # Los runs se recorren de más reciente a más antiguo. Al deduplicar
        # por sucursal + contact_id conservamos la evidencia canónica más reciente.
        for row in reversed(rows):
            source_key = (
                f"{int(row['sucursal_id'])}:{str(row['contact_id'])}"
            )
            if source_key in seen_source_keys:
                continue

            seen_source_keys.add(source_key)
            result.append(
                _serialize_crm_candidate(
                    row,
                    branch_names=branch_names,
                    existing_links=existing_links,
                    phone_contact_ids=phone_contact_ids,
                    active_case_owner_ids=active_case_owner_ids,
                )
            )

    return {
        "period_key": "HISTORICO",
        "sync_run_id": None,
        "rows": result,
    }


def list_crm_candidates(
    month: str,
    *,
    allowed_branch_ids: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    raw_month = str(month or "").strip()
    try:
        month_start = date.fromisoformat(f"{raw_month}-01")
    except ValueError as exc:
        raise ContactCenterValidationError("month debe tener formato YYYY-MM.") from exc

    period_key = f"IVENTAS-{month_start.strftime('%Y-%m')}"
    run = (
        MarketingIventasSyncRunORM.query
        .filter(
            MarketingIventasSyncRunORM.period_key == period_key,
            MarketingIventasSyncRunORM.is_canonical.is_(True),
            MarketingIventasSyncRunORM.status == "COMPLETED",
        )
        .order_by(MarketingIventasSyncRunORM.id.desc())
        .first()
    )
    if run is None:
        return {
            "period_key": period_key,
            "sync_run_id": None,
            "rows": [],
        }

    branch_query = (
        db.session.query(MarketingIventasContactORM.sucursal_id)
        .filter(MarketingIventasContactORM.sync_run_id == run.id)
    )
    if allowed_branch_ids is not None:
        if not allowed_branch_ids:
            return {
                "period_key": period_key,
                "sync_run_id": int(run.id),
                "rows": [],
            }
        branch_query = branch_query.filter(
            MarketingIventasContactORM.sucursal_id.in_(allowed_branch_ids)
        )

    branch_ids = tuple(
        row[0]
        for row in branch_query.distinct().all()
    )
    if not branch_ids:
        return {
            "period_key": period_key,
            "sync_run_id": int(run.id),
            "rows": [],
        }

    statement = build_marketing_lead_contacts_statement(
        iventas_sync_run_id=int(run.id),
        branch_ids=branch_ids,
    )
    rows = db.session.execute(statement).mappings().all()

    (
        existing_links,
        phone_contact_ids,
        active_case_owner_ids,
    ) = _contact_center_crm_link_state()
    branch_names = {
        int(branch.sucursal_id): str(branch.sucursal)
        for branch in Sucursal.query.filter(Sucursal.sucursal_id.in_(branch_ids)).all()
    }

    result = []
    for row in reversed(rows):
        result.append(
            _serialize_crm_candidate(
                row,
                branch_names=branch_names,
                existing_links=existing_links,
                phone_contact_ids=phone_contact_ids,
                active_case_owner_ids=active_case_owner_ids,
            )
        )
        if len(result) >= 500:
            break

    return {
        "period_key": period_key,
        "sync_run_id": int(run.id),
        "rows": result,
    }


def import_crm_candidate(
    contact_row_id: int,
    actor: UserORM,
    *,
    target_contact_id: int | None = None,
    display_name: str | None = None,
    allowed_branch_ids: tuple[int, ...] | None = None,
) -> tuple[ContactCenterContactORM, ContactCenterCaseORM]:
    source = MarketingIventasContactORM.query.get(contact_row_id)
    if source is None:
        raise ContactCenterNotFoundError("Contacto CRM no encontrado.")

    if (
        allowed_branch_ids is not None
        and int(source.sucursal_id) not in set(allowed_branch_ids)
    ):
        raise ContactCenterValidationError(
            "El lead CRM no pertenece a una sucursal autorizada."
        )

    confirmed_display_name = _clean_text(display_name)
    if confirmed_display_name and len(confirmed_display_name) > 255:
        raise ContactCenterValidationError(
            "El nombre del contacto no puede superar 255 caracteres."
        )

    statement = build_marketing_lead_contacts_statement(
        iventas_sync_run_id=int(source.sync_run_id),
        branch_ids=(int(source.sucursal_id),),
    )
    valid_ids = {
        int(row["contact_row_id"])
        for row in db.session.execute(statement).mappings().all()
    }
    if int(source.id) not in valid_ids:
        raise ContactCenterValidationError(
            "El contacto seleccionado no cumple la semántica de lead CRM del Funnel."
        )

    source_key = f"{int(source.sucursal_id)}:{str(source.contact_id)}"
    existing_link = ContactCenterContactLinkORM.query.filter_by(
        source_type="IVENTAS_CONTACT",
        source_key=source_key,
    ).first()

    contact = None
    if existing_link is not None:
        contact = ContactCenterContactORM.query.get(existing_link.contact_id)
    elif target_contact_id is not None:
        contact = ContactCenterContactORM.query.get(target_contact_id)
        if (
            contact is None
            or not contact.is_active
            or contact.merged_into_contact_id is not None
        ):
            raise ContactCenterValidationError(
                "El contacto seleccionado ya no está disponible."
            )

        db.session.add(
            ContactCenterContactLinkORM(
                contact_id=contact.id,
                source_type="IVENTAS_CONTACT",
                source_key=source_key,
                source_row_id=source.id,
                source_metadata_json={
                    "sync_run_id": int(source.sync_run_id),
                    "contact_id": str(source.contact_id),
                    "branch_code": str(source.branch_code),
                    "matched_by": "USER_CONFIRMED",
                },
            )
        )
        db.session.flush()
    else:
        phone = normalize_phone(
            source.phone_mx10
            or source.phone_digits
            or source.phone_raw
        )
        exact_phone_matches = []
        if phone:
            exact_phone_matches = (
                ContactCenterContactORM.query
                .filter(
                    ContactCenterContactORM.is_active.is_(True),
                    ContactCenterContactORM.merged_into_contact_id.is_(None),
                    ContactCenterContactORM.phone_mx10 == phone,
                )
                .order_by(ContactCenterContactORM.updated_at.desc())
                .all()
            )

        if len(exact_phone_matches) == 1:
            contact = exact_phone_matches[0]
            db.session.add(
                ContactCenterContactLinkORM(
                    contact_id=contact.id,
                    source_type="IVENTAS_CONTACT",
                    source_key=source_key,
                    source_row_id=source.id,
                    source_metadata_json={
                        "sync_run_id": int(source.sync_run_id),
                        "contact_id": str(source.contact_id),
                        "branch_code": str(source.branch_code),
                        "matched_by": "PHONE_MX10",
                    },
                )
            )
            db.session.flush()
        elif len(exact_phone_matches) > 1:
            raise ContactCenterDuplicateError(
                [
                    serialize_contact(row)
                    for row in exact_phone_matches[:20]
                ]
            )

    if contact is not None:
        active_case = (
            ContactCenterCaseORM.query
            .filter(
                ContactCenterCaseORM.contact_id == contact.id,
                ContactCenterCaseORM.status != "CLOSED",
            )
            .order_by(ContactCenterCaseORM.updated_at.desc())
            .first()
        )
        if active_case is not None:
            return contact, active_case

        case = ContactCenterCaseORM(
            contact_id=contact.id,
            source_type="CRM",
            source_ref=source_key,
            sucursal_id=source.sucursal_id,
            assigned_user_id=actor.id,
            status="NEW",
            created_by_user_id=actor.id,
        )
        db.session.add(case)
        db.session.flush()
        return contact, case

    phone = source.phone_mx10 or source.phone_digits or source.phone_raw
    duplicates = find_duplicate_contacts(phone=phone)
    if duplicates:
        raise ContactCenterDuplicateError(duplicates)

    contact = ContactCenterContactORM(
        display_name=confirmed_display_name or _clean_text(source.name),
        primary_phone_raw=str(source.phone_raw or phone or ""),
        phone_mx10=normalize_phone(phone),
        preferred_sucursal_id=source.sucursal_id,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    db.session.add(contact)
    db.session.flush()

    db.session.add(
        ContactCenterContactLinkORM(
            contact_id=contact.id,
            source_type="IVENTAS_CONTACT",
            source_key=source_key,
            source_row_id=source.id,
            source_metadata_json={
                "sync_run_id": int(source.sync_run_id),
                "contact_id": str(source.contact_id),
                "branch_code": str(source.branch_code),
            },
        )
    )

    case = ContactCenterCaseORM(
        contact_id=contact.id,
        source_type="CRM",
        source_ref=source_key,
        sucursal_id=source.sucursal_id,
        assigned_user_id=actor.id,
        status="NEW",
        created_by_user_id=actor.id,
    )
    db.session.add(case)
    db.session.flush()
    return contact, case


def merge_contacts(
    *,
    survivor_contact_id: int,
    merged_contact_id: int,
    field_resolution: dict[str, Any],
    actor: UserORM,
) -> ContactCenterContactORM:
    if survivor_contact_id == merged_contact_id:
        raise ContactCenterValidationError(
            "Los contactos a fusionar deben ser distintos."
        )

    survivor = ContactCenterContactORM.query.get(survivor_contact_id)
    merged = ContactCenterContactORM.query.get(merged_contact_id)
    if survivor is None or merged is None:
        raise ContactCenterNotFoundError("Contacto no encontrado.")
    if not survivor.is_active or not merged.is_active:
        raise ContactCenterValidationError(
            "No se puede fusionar un contacto inactivo."
        )

    allowed_fields = {
        "display_name",
        "primary_phone_raw",
        "email",
        "preferred_sucursal_id",
    }
    for field_name, value in (field_resolution or {}).items():
        if field_name not in allowed_fields:
            continue
        setattr(survivor, field_name, value)

    survivor.phone_mx10 = normalize_phone(survivor.primary_phone_raw)
    survivor.updated_by_user_id = actor.id
    survivor.updated_at = _now_utc()

    ContactCenterCaseORM.query.filter_by(
        contact_id=merged.id
    ).update({"contact_id": survivor.id}, synchronize_session=False)
    ContactCenterInteractionORM.query.filter_by(
        contact_id=merged.id
    ).update({"contact_id": survivor.id}, synchronize_session=False)
    ContactCenterAppointmentORM.query.filter_by(
        contact_id=merged.id
    ).update({"contact_id": survivor.id}, synchronize_session=False)

    duplicate_links = (
        ContactCenterContactLinkORM.query
        .filter_by(contact_id=merged.id)
        .order_by(ContactCenterContactLinkORM.id.asc())
        .all()
    )
    for link in duplicate_links:
        conflict = ContactCenterContactLinkORM.query.filter(
            ContactCenterContactLinkORM.contact_id == survivor.id,
            ContactCenterContactLinkORM.source_type == link.source_type,
            ContactCenterContactLinkORM.source_key == link.source_key,
        ).first()
        if conflict is not None:
            db.session.delete(link)
        else:
            link.contact_id = survivor.id

    merged.is_active = False
    merged.merged_into_contact_id = survivor.id
    merged.updated_by_user_id = actor.id
    merged.updated_at = _now_utc()

    db.session.add(
        ContactCenterContactMergeEventORM(
            survivor_contact_id=survivor.id,
            merged_contact_id=merged.id,
            field_resolution_json=field_resolution or {},
            merged_by_user_id=actor.id,
        )
    )
    db.session.flush()
    return survivor


def _is_membership_purchase_row(
    row: VentaTotalSnapshotRowORM,
) -> bool:
    product_key = _normalize_text(row.clave_producto)
    sale_type = _normalize_text(row.tipo)
    description = _normalize_text(row.descripcion)

    if product_key == "MEMBRESIA":
        return True

    if "MEMBRESIA" in sale_type:
        return True

    return any(
        term in description
        for term in MEMBERSHIP_PURCHASE_TERMS
    )


def _parse_venta_total_row_local_datetime(
    row: VentaTotalSnapshotRowORM,
) -> datetime | None:
    try:
        row_date = _parse_row_date(row.fecha)
    except ValueError:
        return None

    raw_time = row.hora
    parsed_time: time | None = None

    if isinstance(raw_time, time):
        parsed_time = raw_time.replace(tzinfo=None)
    elif isinstance(raw_time, datetime):
        parsed_time = raw_time.time().replace(tzinfo=None)
    else:
        text_value = str(raw_time or "").strip()
        try:
            parsed_time = time.fromisoformat(text_value)
        except ValueError:
            for pattern in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
                try:
                    parsed_time = datetime.strptime(
                        text_value,
                        pattern,
                    ).time()
                    break
                except ValueError:
                    continue

    if parsed_time is None:
        return None

    return datetime.combine(
        row_date,
        parsed_time,
        tzinfo=BUSINESS_TZ,
    )


def _resolve_appointment_purchase_match(
    appointment: ContactCenterAppointmentORM,
    *,
    snapshot: VentaTotalSnapshotORM | None = None,
) -> dict[str, Any]:
    contact = appointment.contact
    phone = normalize_phone(
        contact.phone_mx10 or contact.primary_phone_raw
    )
    if phone is None:
        return {"status": "REVIEW"}

    snapshot_value = snapshot
    if snapshot_value is None:
        snapshot_value = (
            VentaTotalSnapshotORM.query
            .filter(
                VentaTotalSnapshotORM.report_type_key == "venta_total",
                VentaTotalSnapshotORM.snapshot_kind == "daily",
                VentaTotalSnapshotORM.is_canonical.is_(True),
            )
            .order_by(
                VentaTotalSnapshotORM.business_date.desc(),
                VentaTotalSnapshotORM.id.desc(),
            )
            .first()
        )

    if snapshot_value is None:
        return {"status": "NOT_FOUND_YET"}

    digits_expr = func.regexp_replace(
        VentaTotalSnapshotRowORM.telefono,
        "[^0-9]",
        "",
        "g",
    )
    candidates = (
        VentaTotalSnapshotRowORM.query
        .filter(
            VentaTotalSnapshotRowORM.snapshot_id == snapshot_value.id,
            func.right(digits_expr, 10) == phone,
        )
        .order_by(VentaTotalSnapshotRowORM.row_index.asc())
        .all()
    )

    scheduled_local = appointment.scheduled_at.astimezone(BUSINESS_TZ)
    grouped: dict[
        str,
        list[tuple[VentaTotalSnapshotRowORM, datetime]],
    ] = defaultdict(list)

    for row in candidates:
        if not _is_valid_status(row.estatus):
            continue
        if not _is_membership_purchase_row(row):
            continue

        transaction_local = _parse_venta_total_row_local_datetime(row)
        if transaction_local is None:
            continue
        if transaction_local < scheduled_local:
            continue

        transaction_key = str(
            row.id_orden or row.folio or f"row:{row.id}"
        ).strip()
        grouped[transaction_key].append((row, transaction_local))

    if not grouped:
        return {"status": "NOT_FOUND_YET"}

    if len(grouped) > 1:
        return {"status": "REVIEW"}

    transaction_rows = next(iter(grouped.values()))
    first_row, first_datetime = min(
        transaction_rows,
        key=lambda item: item[1],
    )
    total = sum(
        (
            Decimal(str(row.total or 0))
            for row, _ in transaction_rows
        ),
        Decimal("0"),
    )
    descriptions = [
        str(row.descripcion or "").strip()
        for row, _ in transaction_rows
        if str(row.descripcion or "").strip()
    ]

    claimed_query = (
        db.session.query(ContactCenterAppointmentORM.id)
        .join(
            VentaTotalSnapshotRowORM,
            ContactCenterAppointmentORM.venta_total_snapshot_row_id
            == VentaTotalSnapshotRowORM.id,
        )
        .filter(
            ContactCenterAppointmentORM.id != appointment.id,
            ContactCenterAppointmentORM.purchase_verification_status
            == "VERIFIED",
        )
    )

    normalized_order_id = str(first_row.id_orden or "").strip()
    normalized_folio = str(first_row.folio or "").strip()
    if normalized_order_id:
        claimed_query = claimed_query.filter(
            VentaTotalSnapshotRowORM.id_orden == normalized_order_id
        )
    elif normalized_folio:
        claimed_query = claimed_query.filter(
            VentaTotalSnapshotRowORM.folio == normalized_folio
        )
    else:
        claimed_query = claimed_query.filter(
            VentaTotalSnapshotRowORM.id == int(first_row.id)
        )

    if claimed_query.first() is not None:
        return {"status": "REVIEW"}

    return {
        "status": "VERIFIED",
        "transaction_key": next(iter(grouped.keys())),
        "snapshot_id": int(snapshot_value.id),
        "snapshot_row_id": int(first_row.id),
        "purchase_at": first_datetime.astimezone(timezone.utc),
        "amount": total,
        "tariff": descriptions[0] if descriptions else None,
    }


def _apply_verified_purchase_match(
    appointment: ContactCenterAppointmentORM,
    match: dict[str, Any],
) -> None:
    appointment.purchase_verification_status = "VERIFIED"
    appointment.venta_total_snapshot_id = int(match["snapshot_id"])
    appointment.venta_total_snapshot_row_id = int(match["snapshot_row_id"])
    appointment.verified_purchase_at = match["purchase_at"]
    appointment.verified_amount = match["amount"]
    appointment.verified_tariff = match["tariff"]
    appointment.updated_at = _now_utc()


def verify_appointment_purchase(
    appointment_id: int,
) -> ContactCenterAppointmentORM:
    appointment = ContactCenterAppointmentORM.query.get(appointment_id)
    if appointment is None:
        raise ContactCenterNotFoundError("Cita no encontrada.")
    if not appointment.purchase_reported:
        raise ContactCenterValidationError(
            "La cita no tiene una compra reportada para validar."
        )

    match = _resolve_appointment_purchase_match(appointment)
    appointment.purchase_verification_status = match["status"]

    if match["status"] == "VERIFIED":
        _apply_verified_purchase_match(appointment, match)

    return appointment


def reconcile_contact_center_appointments_from_venta_total(
    *,
    snapshot_id: int,
) -> dict[str, int]:
    snapshot = VentaTotalSnapshotORM.query.filter_by(
        id=int(snapshot_id)
    ).one_or_none()
    if snapshot is None:
        raise ContactCenterNotFoundError(
            "Snapshot Venta Total no encontrado."
        )
    if (
        snapshot.report_type_key != "venta_total"
        or snapshot.snapshot_kind != "daily"
        or not snapshot.is_canonical
    ):
        raise ContactCenterValidationError(
            "La reconciliación requiere un snapshot canónico daily de Venta Total."
        )

    window_start_local = datetime.combine(
        snapshot.business_date - timedelta(days=30),
        time.min,
        tzinfo=BUSINESS_TZ,
    ).astimezone(timezone.utc)
    window_end_local = datetime.combine(
        snapshot.business_date + timedelta(days=1),
        time.min,
        tzinfo=BUSINESS_TZ,
    ).astimezone(timezone.utc)

    candidates = (
        ContactCenterAppointmentORM.query
        .filter(
            ContactCenterAppointmentORM.scheduled_at >= window_start_local,
            ContactCenterAppointmentORM.scheduled_at < window_end_local,
            or_(
                ContactCenterAppointmentORM.status == "SCHEDULED",
                and_(
                    ContactCenterAppointmentORM.status == "CLOSED",
                    or_(
                        ContactCenterAppointmentORM.outcome.in_(
                            ("NO_SHOW", "ATTENDED_NO_PURCHASE")
                        ),
                        and_(
                            ContactCenterAppointmentORM.outcome
                            == "ATTENDED_PURCHASE_REPORTED",
                            ContactCenterAppointmentORM.purchase_verification_status
                            != "VERIFIED",
                        ),
                    ),
                ),
            ),
        )
        .order_by(ContactCenterAppointmentORM.scheduled_at.desc())
        .all()
    )

    result = {
        "appointments_scanned": 0,
        "appointments_corrected": 0,
        "review_required": 0,
        "not_found": 0,
    }
    used_transactions: set[tuple[int, str]] = set()

    for appointment in candidates:
        result["appointments_scanned"] += 1
        match = _resolve_appointment_purchase_match(
            appointment,
            snapshot=snapshot,
        )

        if match["status"] == "REVIEW":
            result["review_required"] += 1
            continue
        if match["status"] != "VERIFIED":
            result["not_found"] += 1
            continue

        transaction_identity = (
            int(match["snapshot_id"]),
            str(match["transaction_key"]),
        )
        if transaction_identity in used_transactions:
            result["review_required"] += 1
            continue
        used_transactions.add(transaction_identity)

        if appointment.outcome == "ATTENDED_PURCHASE_REPORTED":
            _apply_verified_purchase_match(appointment, match)
            result["appointments_corrected"] += 1
            continue

        previous_status = appointment.status
        previous_outcome = appointment.outcome
        previous_case_status = appointment.case.status

        _apply_appointment_result(
            appointment,
            outcome="ATTENDED_PURCHASE_REPORTED",
            changed_by_user_id=None,