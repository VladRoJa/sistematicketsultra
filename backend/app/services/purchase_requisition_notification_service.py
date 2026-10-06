from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.purchase_requisition import (
    PurchaseRequisitionEventORM,
    PurchaseRequisitionEventType,
    PurchaseRequisitionFinanceApproverORM,
    PurchaseRequisitionNotificationORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionStatus,
)
from app.models.user_model import UserORM
from app.utils.email_sender import send_email_html


REVIEW_RECIPIENT_ROLES = ("GERENCIA DEPORTIVA",)
MAINTENANCE_RECIPIENT_ROLES = (
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
    "AUX_MANTENIMIENTO",
)


class PurchaseRequisitionNotificationError(RuntimeError):
    pass


def _session(session: Session | None):
    return session if session is not None else db.session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_email(value: object) -> str | None:
    email = str(value or "").strip().lower()
    return email or None


def _users_by_roles(
    target_session,
    roles: tuple[str, ...],
) -> list[tuple[int, str]]:
    rows = target_session.execute(
        select(UserORM.id, UserORM.email).where(
            func.upper(func.trim(UserORM.rol)).in_(roles),
            UserORM.email.is_not(None),
            func.length(func.trim(UserORM.email)) > 0,
        )
    ).all()
    return [
        (int(user_id), email)
        for user_id, raw_email in rows
        if (email := _normalized_email(raw_email))
    ]


def _branch_managers(
    target_session,
    branch_id: int,
) -> list[tuple[int, str]]:
    rows = target_session.execute(
        select(UserORM.id, UserORM.email).where(
            func.upper(func.trim(UserORM.rol)) == "GERENTE",
            UserORM.sucursal_id == int(branch_id),
            UserORM.email.is_not(None),
            func.length(func.trim(UserORM.email)) > 0,
        )
    ).all()
    return [
        (int(user_id), email)
        for user_id, raw_email in rows
        if (email := _normalized_email(raw_email))
    ]


def _finance_approvers(
    target_session,
) -> list[tuple[int, str]]:
    rows = target_session.execute(
        select(UserORM.id, UserORM.email)
        .join(
            PurchaseRequisitionFinanceApproverORM,
            PurchaseRequisitionFinanceApproverORM.user_id
            == UserORM.id,
        )
        .where(
            PurchaseRequisitionFinanceApproverORM.is_active.is_(True),
            UserORM.email.is_not(None),
            func.length(func.trim(UserORM.email)) > 0,
        )
    ).all()
    return [
        (int(user_id), email)
        for user_id, raw_email in rows
        if (email := _normalized_email(raw_email))
    ]


def _requester(
    target_session,
    requisition: PurchaseRequisitionORM,
) -> list[tuple[int, str]]:
    row = target_session.execute(
        select(UserORM.id, UserORM.email).where(
            UserORM.id == int(requisition.created_by_user_id),
            UserORM.email.is_not(None),
            func.length(func.trim(UserORM.email)) > 0,
        )
    ).one_or_none()
    if row is None:
        return []
    email = _normalized_email(row.email)
    return [(int(row.id), email)] if email else []


def resolve_notification_recipients(
    target_session,
    requisition: PurchaseRequisitionORM,
    event_type: str,
) -> list[tuple[int, str]]:
    if event_type in {
        PurchaseRequisitionEventType.CREATED,
        PurchaseRequisitionEventType.RESUBMITTED,
    }:
        candidates = _users_by_roles(
            target_session,
            REVIEW_RECIPIENT_ROLES,
        )
    elif event_type in {
        PurchaseRequisitionEventType.INFO_REQUESTED,
        PurchaseRequisitionEventType.REJECTED,
    }:
        candidates = _requester(
            target_session,
            requisition,
        )
    elif event_type == PurchaseRequisitionEventType.APPROVED:
        candidates = (
            _requester(target_session, requisition)
            + _users_by_roles(
                target_session,
                MAINTENANCE_RECIPIENT_ROLES,
            )
        )
    elif event_type == (
        PurchaseRequisitionEventType
        .QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL
    ):
        candidates = _finance_approvers(target_session)
    elif event_type in {
        PurchaseRequisitionEventType.QUOTE_APPROVED_BY_FINANCE,
        PurchaseRequisitionEventType.QUOTE_REJECTED_BY_FINANCE,
    }:
        candidates = _users_by_roles(
            target_session,
            MAINTENANCE_RECIPIENT_ROLES,
        )
    elif event_type == (
        PurchaseRequisitionEventType
        .FINAL_DESTINATION_SHIPMENT_STARTED
    ):
        candidates = _branch_managers(
            target_session,
            requisition.sucursal_id,
        )
    elif event_type == (
        PurchaseRequisitionEventType.RECEIPT_ISSUE_REPORTED
    ):
        candidates = _users_by_roles(
            target_session,
            MAINTENANCE_RECIPIENT_ROLES,
        )
    elif event_type == PurchaseRequisitionEventType.RECEIVED:
        candidates = (
            _users_by_roles(
                target_session,
                MAINTENANCE_RECIPIENT_ROLES,
            )
            + _users_by_roles(
                target_session,
                REVIEW_RECIPIENT_ROLES,
            )
        )
    elif event_type == (
        PurchaseRequisitionEventType.ADMINISTRATIVE_CORRECTION
    ):
        if requisition.status == PurchaseRequisitionStatus.PENDING_REVIEW:
            candidates = _users_by_roles(
                target_session,
                REVIEW_RECIPIENT_ROLES,
            )
        elif requisition.status in {
            PurchaseRequisitionStatus.IN_QUOTATION,
            PurchaseRequisitionStatus.PAYMENT_REQUESTED,
            PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS,
            PurchaseRequisitionStatus.IMPORT_IN_PROGRESS,
            PurchaseRequisitionStatus.RECEIPT_ISSUE,
        }:
            candidates = _users_by_roles(
                target_session,
                MAINTENANCE_RECIPIENT_ROLES,
            )
        elif requisition.status == (
            PurchaseRequisitionStatus.QUOTE_PENDING_FINANCE_APPROVAL
        ):
            candidates = _finance_approvers(target_session)
        elif requisition.status == (
            PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT
        ):
            latest_correction = target_session.execute(
                select(PurchaseRequisitionEventORM)
                .where(
                    PurchaseRequisitionEventORM.requisition_id
                    == int(requisition.id),
                    PurchaseRequisitionEventORM.event_type
                    == PurchaseRequisitionEventType.ADMINISTRATIVE_CORRECTION,
                )
                .order_by(PurchaseRequisitionEventORM.id.desc())
                .limit(1)
            ).scalar_one_or_none()

            candidates = _branch_managers(
                target_session,
                requisition.sucursal_id,
            )
            if (
                latest_correction is not None
                and latest_correction.from_status
                == PurchaseRequisitionStatus.CLOSED
            ):
                candidates += _users_by_roles(
                    target_session,
                    MAINTENANCE_RECIPIENT_ROLES,
                )
        else:
            candidates = []
    else:
        candidates = []

    by_email: dict[str, tuple[int, str]] = {}
    for user_id, email in candidates:
        by_email.setdefault(email, (user_id, email))
    return list(by_email.values())


def _subject(
    requisition: PurchaseRequisitionORM,
    event_type: str,
) -> str:
    labels = {
        PurchaseRequisitionEventType.CREATED: "Nueva requisición",
        PurchaseRequisitionEventType.INFO_REQUESTED: (
            "Información requerida"
        ),
        PurchaseRequisitionEventType.RESUBMITTED: (
            "Requisición reenviada"
        ),
        PurchaseRequisitionEventType.APPROVED: (
            "Requisición aprobada"
        ),
        PurchaseRequisitionEventType.REJECTED: (
            "Requisición rechazada"
        ),
        (
            PurchaseRequisitionEventType
            .QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL
        ): "Cotización pendiente de aprobación",
        PurchaseRequisitionEventType.QUOTE_APPROVED_BY_FINANCE: (
            "Cotización financiera aprobada"
        ),
        PurchaseRequisitionEventType.QUOTE_REJECTED_BY_FINANCE: (
            "Cotización financiera rechazada"
        ),
        (
            PurchaseRequisitionEventType
            .FINAL_DESTINATION_SHIPMENT_STARTED
        ): "Envío listo para confirmación de sucursal",
        PurchaseRequisitionEventType.RECEIPT_ISSUE_REPORTED: (
            "Incidencia de recepción reportada"
        ),
        PurchaseRequisitionEventType.RECEIVED: (
            "Requisición recibida y cerrada"
        ),
        PurchaseRequisitionEventType.ADMINISTRATIVE_CORRECTION: (
            "Corrección administrativa de requisición"
        ),
    }
    label = labels.get(event_type, "Actualización de requisición")
    return f"{label} · {requisition.public_id}"


def _html(
    requisition: PurchaseRequisitionORM,
    event_type: str,
) -> str:
    public_id = escape(str(requisition.public_id))
    status = escape(str(requisition.status))
    event = escape(str(event_type))
    return (
        "<p>Suite Ultra — Requisiciones</p>"
        f"<p><strong>{public_id}</strong></p>"
        f"<p>Evento: {event}</p>"
        f"<p>Estado actual: {status}</p>"
        "<p>Consulta el expediente en Suite Ultra.</p>"
    )


def _get_or_create_delivery(
    target_session,
    *,
    event_id: int,
    recipient_user_id: int,
    recipient_email: str,
) -> PurchaseRequisitionNotificationORM:
    existing = target_session.execute(
        select(PurchaseRequisitionNotificationORM).where(
            PurchaseRequisitionNotificationORM.event_id
            == int(event_id),
            PurchaseRequisitionNotificationORM.recipient_email
            == recipient_email,
            PurchaseRequisitionNotificationORM.channel == "EMAIL",
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    delivery = PurchaseRequisitionNotificationORM(
        event_id=int(event_id),
        recipient_user_id=int(recipient_user_id),
        recipient_email=recipient_email,
        channel="EMAIL",
        status="PENDING",
    )
    try:
        with target_session.begin_nested():
            target_session.add(delivery)
            target_session.flush()
        return delivery
    except IntegrityError:
        return target_session.execute(
            select(PurchaseRequisitionNotificationORM).where(
                PurchaseRequisitionNotificationORM.event_id
                == int(event_id),
                PurchaseRequisitionNotificationORM.recipient_email
                == recipient_email,
                PurchaseRequisitionNotificationORM.channel == "EMAIL",
            )
        ).scalar_one()


def dispatch_event_notifications(
    event_id: int,
    *,
    session: Session | None = None,
    sender: Callable[[list[str], str, str], None] = send_email_html,
) -> list[PurchaseRequisitionNotificationORM]:
    target_session = _session(session)
    event = target_session.get(
        PurchaseRequisitionEventORM,
        int(event_id),
    )
    if event is None:
        raise PurchaseRequisitionNotificationError(
            "Evento de requisición no encontrado."
        )

    requisition = target_session.get(
        PurchaseRequisitionORM,
        int(event.requisition_id),
    )
    if requisition is None:
        raise PurchaseRequisitionNotificationError(
            "Requisición del evento no encontrada."
        )

    recipients = resolve_notification_recipients(
        target_session,
        requisition,
        event.event_type,
    )

    deliveries = [
        _get_or_create_delivery(
            target_session,
            event_id=event.id,
            recipient_user_id=user_id,
            recipient_email=email,
        )
        for user_id, email in recipients
    ]
    target_session.commit()

    for delivery in deliveries:
        if delivery.status == "SENT":
            continue

        delivery.attempts = int(delivery.attempts or 0) + 1
        delivery.last_error = None

        try:
            sender(
                [delivery.recipient_email],
                _subject(requisition, event.event_type),
                _html(requisition, event.event_type),
            )
        except Exception as exc:
            delivery.status = "FAILED"
            delivery.last_error = str(exc)[:2000]
            target_session.commit()
            continue

        delivery.status = "SENT"
        delivery.sent_at = _utc_now()
        delivery.last_error = None
        target_session.commit()

    return deliveries


def latest_event_id(
    requisition_id: int,
    event_type: str,
    *,
    session: Session | None = None,
) -> int | None:
    target_session = _session(session)
    return target_session.execute(
        select(PurchaseRequisitionEventORM.id)
        .where(
            PurchaseRequisitionEventORM.requisition_id
            == int(requisition_id),
            PurchaseRequisitionEventORM.event_type == event_type,
        )
        .order_by(PurchaseRequisitionEventORM.id.desc())
        .limit(1)
    ).scalar_one_or_none()
