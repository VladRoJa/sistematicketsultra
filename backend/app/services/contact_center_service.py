from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models.contact_center import (
    ContactCenterAppointmentORM,
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
from app.services.marketing_sales_funnel_service import _parse_row_date
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

    assigned_user_id = payload.get("assigned_user_id") or actor.id
    try:
        assigned_user_id = int(assigned_user_id)
    except (TypeError, ValueError) as exc:
        raise ContactCenterValidationError("Agente asignado inválido.") from exc

    assigned_user = UserORM.get_by_id(assigned_user_id)
    if not has_contact_center_access(assigned_user):
        raise ContactCenterValidationError(
            "El agente seleccionado no tiene acceso a Contact Center."
        )

    case = ContactCenterCaseORM(
        contact_id=contact.id,
        source_type=source_type,