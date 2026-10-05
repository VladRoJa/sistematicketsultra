from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.purchase_requisition import (
    PurchaseRequisitionEventORM,
    PurchaseRequisitionEventType,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionPriority,
    PurchaseRequisitionReason,
    PurchaseRequisitionStatus,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionNotFoundError,
    PurchaseRequisitionValidationError,
    _parse_items,
    _required_text,
    _validate_choice,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    can_purchase_requisition_review,
)


class PurchaseRequisitionConflictError(RuntimeError):
    pass


def _session(session: Session | None):
    return session if session is not None else db.session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _locked_requisition_stmt(requisition_id: int):
    return (
        select(PurchaseRequisitionORM)
        .where(PurchaseRequisitionORM.id == int(requisition_id))
        .with_for_update()
    )


def _load(
    requisition_id: int,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    target_session = _session(session)
    row = target_session.execute(
        _locked_requisition_stmt(requisition_id)
    ).scalar_one_or_none()
    if row is None:
        raise PurchaseRequisitionNotFoundError(
            "Requisición no encontrada."
        )
    return row


def _require_status(
    requisition: PurchaseRequisitionORM,
    expected: str,
) -> None:
    if requisition.status != expected:
        raise PurchaseRequisitionConflictError(
            "La requisición ya no está en un estado válido "
            "para esta acción."
        )


def _append_event(
    requisition: PurchaseRequisitionORM,
    *,
    event_type: str,
    actor_user_id: int,
    from_status: str | None,
    to_status: str | None,
    comment: str | None = None,
    metadata_json: dict | None = None,
) -> None:
    requisition.events.append(
        PurchaseRequisitionEventORM(
            event_type=event_type,
            actor_user_id=int(actor_user_id),
            from_status=from_status,
            to_status=to_status,
            comment=comment,
            metadata_json=metadata_json,
        )
    )


def requester_edit_purchase_requisition(
    requisition_id: int,
    payload: dict,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.NEEDS_INFO,
    )

    if int(requisition.created_by_user_id) != int(actor.id):
        raise PurchaseRequisitionAuthorizationError(
            "Sólo el solicitante puede corregir esta requisición."
        )

    if not isinstance(payload, dict):
        raise PurchaseRequisitionValidationError(
            "Payload inválido."
        )

    if "reason" in payload:
        requisition.reason = _validate_choice(
            payload.get("reason"),
            "reason",
            PurchaseRequisitionReason.ALL,
        )
    if "priority" in payload:
        requisition.priority = _validate_choice(
            payload.get("priority"),
            "priority",
            PurchaseRequisitionPriority.ALL,
        )
    if "justification" in payload:
        requisition.justification = _required_text(
            payload.get("justification"),
            "justification",
        )
    if "items" in payload:
        parsed_items = _parse_items(payload.get("items"))
        requisition.items.clear()
        for item in parsed_items:
            requisition.items.append(
                PurchaseRequisitionItemORM(**item)
            )

    target_session.flush()
    return requisition


def request_info_purchase_requisition(
    requisition_id: int,
    comment: object,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    if not can_purchase_requisition_review(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No tienes permiso para solicitar información."
        )

    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.PENDING_REVIEW,
    )
    normalized_comment = _required_text(
        comment,
        "comment",
    )

    previous_status = requisition.status
    requisition.status = PurchaseRequisitionStatus.NEEDS_INFO
    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.INFO_REQUESTED,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_comment,
    )
    target_session.flush()
    return requisition


def resubmit_purchase_requisition(
    requisition_id: int,
    actor,
    *,
    comment: object = None,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.NEEDS_INFO,
    )

    if int(requisition.created_by_user_id) != int(actor.id):
        raise PurchaseRequisitionAuthorizationError(
            "Sólo el solicitante puede reenviar esta requisición."
        )

    normalized_comment = str(comment or "").strip() or None
    previous_status = requisition.status
    requisition.status = PurchaseRequisitionStatus.PENDING_REVIEW
    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.RESUBMITTED,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_comment,
    )
    target_session.flush()
    return requisition


def approve_purchase_requisition(
    requisition_id: int,
    actor,
    *,
    comment: object = None,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    if not can_purchase_requisition_review(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No tienes permiso para aprobar requisiciones."
        )

    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.PENDING_REVIEW,
    )

    normalized_comment = str(comment or "").strip() or None
    previous_status = requisition.status
    requisition.status = PurchaseRequisitionStatus.IN_QUOTATION
    requisition.approved_by_user_id = int(actor.id)
    requisition.approved_at = _utc_now()
    requisition.approval_comment = normalized_comment

    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.APPROVED,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_comment,
    )
    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.ROUTED_TO_MAINTENANCE,
        actor_user_id=int(actor.id),
        from_status=requisition.status,
        to_status=requisition.status,
        comment=None,
    )
    target_session.flush()
    return requisition


def reject_purchase_requisition(
    requisition_id: int,
    reason: object,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    if not can_purchase_requisition_review(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No tienes permiso para rechazar requisiciones."
        )

    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.PENDING_REVIEW,
    )
    normalized_reason = _required_text(
        reason,
        "reason",
    )

    previous_status = requisition.status
    requisition.status = PurchaseRequisitionStatus.REJECTED
    requisition.rejected_at = _utc_now()

    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.REJECTED,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_reason,
    )
    target_session.flush()
    return requisition
