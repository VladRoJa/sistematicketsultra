from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.purchase_requisition import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionAttachmentType,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionEventType,
    PurchaseRequisitionFinanceApproverORM,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionPriority,
    PurchaseRequisitionQuoteFinanceStatus,
    PurchaseRequisitionQuoteORM,
    PurchaseRequisitionReceiptIssueType,
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
    can_purchase_requisition_admin_correct,
    can_purchase_requisition_approve_quote,
    can_purchase_requisition_confirm_receipt,
    can_purchase_requisition_manage_logistics,
    can_purchase_requisition_manage_quotation,
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


def _selected_quote_for_requisition(
    session: Session,
    requisition_id: int,
) -> PurchaseRequisitionQuoteORM | None:
    return session.execute(
        select(PurchaseRequisitionQuoteORM)
        .where(
            PurchaseRequisitionQuoteORM.requisition_id
            == int(requisition_id),
            PurchaseRequisitionQuoteORM.is_selected.is_(True),
        )
        .with_for_update()
    ).scalar_one_or_none()


def _has_active_finance_approver(session: Session) -> bool:
    approver_id = session.execute(
        select(PurchaseRequisitionFinanceApproverORM.id)
        .where(
            PurchaseRequisitionFinanceApproverORM.is_active.is_(True)
        )
        .limit(1)
    ).scalar_one_or_none()
    return approver_id is not None


def submit_purchase_requisition_quote_for_finance(
    requisition_id: int,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    if not can_purchase_requisition_manage_quotation(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para enviar cotizaciones a aprobación financiera."
        )

    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.IN_QUOTATION,
    )

    quote = _selected_quote_for_requisition(
        target_session,
        requisition.id,
    )
    if quote is None:
        raise PurchaseRequisitionValidationError(
            "Debes seleccionar una cotización antes de enviarla a Finanzas."
        )
    if (
        quote.finance_status
        != PurchaseRequisitionQuoteFinanceStatus.DRAFT
    ):
        raise PurchaseRequisitionConflictError(
            "La cotización seleccionada no está disponible para envío."
        )
    if not _has_active_finance_approver(target_session):
        raise PurchaseRequisitionConflictError(
            "No hay aprobador financiero activo configurado."
        )

    now = _utc_now()
    previous_status = requisition.status
    requisition.status = (
        PurchaseRequisitionStatus.QUOTE_PENDING_FINANCE_APPROVAL
    )
    quote.finance_status = PurchaseRequisitionQuoteFinanceStatus.PENDING
    quote.finance_submitted_by_user_id = int(actor.id)
    quote.finance_submitted_at = now
    quote.finance_decided_by_user_id = None
    quote.finance_decided_at = None
    quote.finance_comment = None

    _append_event(
        requisition,
        event_type=(
            PurchaseRequisitionEventType
            .QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL
        ),
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        metadata_json={
            "quote_id": int(quote.id),
            "attachment_id": int(quote.attachment_id),
        },
    )
    target_session.flush()
    return requisition


def approve_purchase_requisition_quote_by_finance(
    requisition_id: int,
    actor,
    *,
    comment: object = None,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    target_session = _session(session)
    if not can_purchase_requisition_approve_quote(
        actor,
        session=target_session,
    ):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para aprobar cotizaciones financieras."
        )

    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.QUOTE_PENDING_FINANCE_APPROVAL,
    )

    quote = _selected_quote_for_requisition(
        target_session,
        requisition.id,
    )
    if (
        quote is None
        or quote.finance_status
        != PurchaseRequisitionQuoteFinanceStatus.PENDING
    ):
        raise PurchaseRequisitionConflictError(
            "No existe una cotización pendiente válida para decidir."
        )

    normalized_comment = str(comment or "").strip() or None
    now = _utc_now()
    previous_status = requisition.status

    quote.finance_status = PurchaseRequisitionQuoteFinanceStatus.APPROVED
    quote.finance_decided_by_user_id = int(actor.id)
    quote.finance_decided_at = now
    quote.finance_comment = normalized_comment
    requisition.status = PurchaseRequisitionStatus.PAYMENT_REQUESTED

    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.QUOTE_APPROVED_BY_FINANCE,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_comment,
        metadata_json={
            "quote_id": int(quote.id),
            "attachment_id": int(quote.attachment_id),
        },
    )
    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.PAYMENT_REQUESTED,
        actor_user_id=int(actor.id),
        from_status=requisition.status,
        to_status=requisition.status,
        metadata_json={
            "quote_id": int(quote.id),
        },
    )
    target_session.flush()
    return requisition


def reject_purchase_requisition_quote_by_finance(
    requisition_id: int,
    reason: object,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    target_session = _session(session)
    if not can_purchase_requisition_approve_quote(
        actor,
        session=target_session,
    ):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para rechazar cotizaciones financieras."
        )

    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.QUOTE_PENDING_FINANCE_APPROVAL,
    )

    quote = _selected_quote_for_requisition(
        target_session,
        requisition.id,
    )
    if (
        quote is None
        or quote.finance_status
        != PurchaseRequisitionQuoteFinanceStatus.PENDING
    ):
        raise PurchaseRequisitionConflictError(
            "No existe una cotización pendiente válida para decidir."
        )

    normalized_reason = _required_text(reason, "reason")
    now = _utc_now()
    previous_status = requisition.status

    quote.finance_status = PurchaseRequisitionQuoteFinanceStatus.REJECTED
    quote.finance_decided_by_user_id = int(actor.id)
    quote.finance_decided_at = now
    quote.finance_comment = normalized_reason
    quote.is_selected = False
    quote.selected_by_user_id = None
    quote.selected_at = None
    requisition.status = PurchaseRequisitionStatus.IN_QUOTATION

    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.QUOTE_REJECTED_BY_FINANCE,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_reason,
        metadata_json={
            "quote_id": int(quote.id),
            "attachment_id": int(quote.attachment_id),
        },
    )
    target_session.flush()
    return requisition


_LOGISTICS_TARGET_STATUSES = (
    PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS,
    PurchaseRequisitionStatus.IMPORT_IN_PROGRESS,
    PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT,
)


def _require_approved_selected_quote(
    session: Session,
    requisition_id: int,
) -> PurchaseRequisitionQuoteORM:
    quote = _selected_quote_for_requisition(
        session,
        requisition_id,
    )
    if (
        quote is None
        or quote.finance_status
        != PurchaseRequisitionQuoteFinanceStatus.APPROVED
    ):
        raise PurchaseRequisitionConflictError(
            "La requisición no tiene una cotización financiera aprobada vigente."
        )
    return quote


def advance_purchase_requisition_logistics(
    requisition_id: int,
    target_status: object,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    if not can_purchase_requisition_manage_logistics(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para avanzar la logística de requisiciones."
        )

    normalized_target = _validate_choice(
        target_status,
        "target_status",
        _LOGISTICS_TARGET_STATUSES,
    )

    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_approved_selected_quote(
        target_session,
        requisition.id,
    )

    current_status = requisition.status
    actor_user_id = int(actor.id)

    if current_status == PurchaseRequisitionStatus.PAYMENT_REQUESTED:
        if normalized_target != PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS:
            raise PurchaseRequisitionConflictError(
                "Desde PAYMENT_REQUESTED solo puede avanzarse a "
                "SHIPPING_IN_PROGRESS."
            )

        requisition.status = PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS
        _append_event(
            requisition,
            event_type=PurchaseRequisitionEventType.SHIPPING_STARTED,
            actor_user_id=actor_user_id,
            from_status=current_status,
            to_status=requisition.status,
        )

    elif current_status == PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS:
        if normalized_target == PurchaseRequisitionStatus.IMPORT_IN_PROGRESS:
            requisition.status = PurchaseRequisitionStatus.IMPORT_IN_PROGRESS
            _append_event(
                requisition,
                event_type=PurchaseRequisitionEventType.IMPORT_STARTED,
                actor_user_id=actor_user_id,
                from_status=current_status,
                to_status=requisition.status,
                metadata_json={
                    "import_required": True,
                },
            )

        elif (
            normalized_target
            == PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT
        ):
            _append_event(
                requisition,
                event_type=(
                    PurchaseRequisitionEventType.IMPORT_NOT_APPLICABLE
                ),
                actor_user_id=actor_user_id,
                from_status=current_status,
                to_status=current_status,
                metadata_json={
                    "import_required": False,
                },
            )
            requisition.status = (
                PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT
            )
            _append_event(
                requisition,
                event_type=(
                    PurchaseRequisitionEventType
                    .FINAL_DESTINATION_SHIPMENT_STARTED
                ),
                actor_user_id=actor_user_id,
                from_status=current_status,
                to_status=requisition.status,
                metadata_json={
                    "import_required": False,
                },
            )

        else:
            raise PurchaseRequisitionConflictError(
                "Desde SHIPPING_IN_PROGRESS solo puede avanzarse a "
                "IMPORT_IN_PROGRESS o FINAL_DESTINATION_SHIPMENT."
            )

    elif current_status == PurchaseRequisitionStatus.IMPORT_IN_PROGRESS:
        if (
            normalized_target
            != PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT
        ):
            raise PurchaseRequisitionConflictError(
                "Desde IMPORT_IN_PROGRESS solo puede avanzarse a "
                "FINAL_DESTINATION_SHIPMENT."
            )

        requisition.status = (
            PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT
        )
        _append_event(
            requisition,
            event_type=(
                PurchaseRequisitionEventType
                .FINAL_DESTINATION_SHIPMENT_STARTED
            ),
            actor_user_id=actor_user_id,
            from_status=current_status,
            to_status=requisition.status,
            metadata_json={
                "import_required": True,
            },
        )

    else:
        raise PurchaseRequisitionConflictError(
            "La requisición no está en un estado logístico avanzable."
        )

    target_session.flush()
    return requisition


def _normalize_evidence_attachment_ids(
    value: object,
    *,
    field: str,
    required: bool,
) -> list[int]:
    if value is None:
        if required:
            raise PurchaseRequisitionValidationError(
                f"{field} es obligatorio."
            )
        return []

    if not isinstance(value, (list, tuple)):
        raise PurchaseRequisitionValidationError(
            f"{field} debe ser una lista."
        )

    normalized: list[int] = []
    seen: set[int] = set()
    for raw in value:
        if isinstance(raw, bool):
            raise PurchaseRequisitionValidationError(
                f"{field} contiene un id inválido."
            )
        try:
            attachment_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise PurchaseRequisitionValidationError(
                f"{field} contiene un id inválido."
            ) from exc
        if attachment_id <= 0:
            raise PurchaseRequisitionValidationError(
                f"{field} contiene un id inválido."
            )
        if attachment_id not in seen:
            normalized.append(attachment_id)
            seen.add(attachment_id)

    if required and not normalized:
        raise PurchaseRequisitionValidationError(
            f"{field} debe contener al menos una evidencia."
        )
    return normalized


def _validate_receipt_evidence_attachments(
    session: Session,
    requisition_id: int,
    attachment_ids: list[int],
    expected_type: str,
) -> None:
    if not attachment_ids:
        return

    existing_ids = set(
        session.scalars(
            select(PurchaseRequisitionAttachmentORM.id).where(
                PurchaseRequisitionAttachmentORM.id.in_(attachment_ids),
                PurchaseRequisitionAttachmentORM.requisition_id
                == int(requisition_id),
                PurchaseRequisitionAttachmentORM.deleted_at.is_(None),
                PurchaseRequisitionAttachmentORM.attachment_type
                == expected_type,
            )
        ).all()
    )
    if existing_ids != set(attachment_ids):
        raise PurchaseRequisitionValidationError(
            "La evidencia no pertenece a la requisición "
            "o tiene un tipo inválido."
        )


def confirm_purchase_requisition_receipt(
    requisition_id: int,
    actor,
    *,
    comment: object = None,
    evidence_attachment_ids: object = None,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT,
    )

    if not can_purchase_requisition_confirm_receipt(
        actor,
        requisition,
    ):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para confirmar la recepción de esta requisición."
        )

    _require_approved_selected_quote(
        target_session,
        requisition.id,
    )

    normalized_evidence = _normalize_evidence_attachment_ids(
        evidence_attachment_ids,
        field="evidence_attachment_ids",
        required=False,
    )
    _validate_receipt_evidence_attachments(
        target_session,
        requisition.id,
        normalized_evidence,
        PurchaseRequisitionAttachmentType.RECEIPT_EVIDENCE,
    )

    normalized_comment = str(comment or "").strip() or None
    previous_status = requisition.status
    requisition.status = PurchaseRequisitionStatus.CLOSED

    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.RECEIVED,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_comment,
        metadata_json={
            "evidence_attachment_ids": normalized_evidence,
        },
    )
    target_session.flush()
    return requisition


def report_purchase_requisition_receipt_issue(
    requisition_id: int,
    issue_type: object,
    comment: object,
    evidence_attachment_ids: object,
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
        PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT,
    )

    if not can_purchase_requisition_confirm_receipt(
        actor,
        requisition,
    ):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para reportar incidencias de recepción "
            "en esta requisición."
        )

    _require_approved_selected_quote(
        target_session,
        requisition.id,
    )

    normalized_issue_type = _validate_choice(
        issue_type,
        "issue_type",
        PurchaseRequisitionReceiptIssueType.ALL,
    )
    normalized_comment = _required_text(comment, "comment")
    normalized_evidence = _normalize_evidence_attachment_ids(
        evidence_attachment_ids,
        field="evidence_attachment_ids",
        required=True,
    )
    _validate_receipt_evidence_attachments(
        target_session,
        requisition.id,
        normalized_evidence,
        PurchaseRequisitionAttachmentType.RECEIPT_ISSUE_EVIDENCE,
    )

    previous_status = requisition.status
    requisition.status = PurchaseRequisitionStatus.RECEIPT_ISSUE

    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.RECEIPT_ISSUE_REPORTED,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_comment,
        metadata_json={
            "issue_type": normalized_issue_type,
            "evidence_attachment_ids": normalized_evidence,
        },
    )
    target_session.flush()
    return requisition


def resume_purchase_requisition_logistics(
    requisition_id: int,
    comment: object,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    if not can_purchase_requisition_manage_logistics(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para reanudar la logística de requisiciones."
        )

    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )
    _require_status(
        requisition,
        PurchaseRequisitionStatus.RECEIPT_ISSUE,
    )
    _require_approved_selected_quote(
        target_session,
        requisition.id,
    )

    normalized_comment = _required_text(comment, "comment")
    previous_status = requisition.status
    requisition.status = PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS

    _append_event(
        requisition,
        event_type=(
            PurchaseRequisitionEventType.RECEIPT_ISSUE_RESOLUTION_STARTED
        ),
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_comment,
    )
    target_session.flush()
    return requisition


_ADMINISTRATIVE_CORRECTION_TARGETS = {
    PurchaseRequisitionStatus.NEEDS_INFO: frozenset({
        PurchaseRequisitionStatus.PENDING_REVIEW,
    }),
    PurchaseRequisitionStatus.REJECTED: frozenset({
        PurchaseRequisitionStatus.PENDING_REVIEW,
    }),
    PurchaseRequisitionStatus.IN_QUOTATION: frozenset({
        PurchaseRequisitionStatus.PENDING_REVIEW,
    }),
    PurchaseRequisitionStatus.QUOTE_PENDING_FINANCE_APPROVAL: frozenset({
        PurchaseRequisitionStatus.IN_QUOTATION,
    }),
    PurchaseRequisitionStatus.PAYMENT_REQUESTED: frozenset({
        PurchaseRequisitionStatus.QUOTE_PENDING_FINANCE_APPROVAL,
    }),
    PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS: frozenset({
        PurchaseRequisitionStatus.PAYMENT_REQUESTED,
    }),
    PurchaseRequisitionStatus.IMPORT_IN_PROGRESS: frozenset({
        PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS,
    }),
    PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT: frozenset({
        PurchaseRequisitionStatus.IMPORT_IN_PROGRESS,
        PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS,
    }),
    PurchaseRequisitionStatus.RECEIPT_ISSUE: frozenset({
        PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT,
    }),
    PurchaseRequisitionStatus.CLOSED: frozenset({
        PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT,
        PurchaseRequisitionStatus.RECEIPT_ISSUE,
    }),
}


def _event_exists(
    session: Session,
    requisition_id: int,
    event_type: str,
) -> bool:
    event_id = session.execute(
        select(PurchaseRequisitionEventORM.id)
        .where(
            PurchaseRequisitionEventORM.requisition_id
            == int(requisition_id),
            PurchaseRequisitionEventORM.event_type == event_type,
        )
        .limit(1)
    ).scalar_one_or_none()
    return event_id is not None


def _latest_event(
    session: Session,
    requisition_id: int,
    event_type: str,
) -> PurchaseRequisitionEventORM | None:
    return session.execute(
        select(PurchaseRequisitionEventORM)
        .where(
            PurchaseRequisitionEventORM.requisition_id
            == int(requisition_id),
            PurchaseRequisitionEventORM.event_type == event_type,
        )
        .order_by(PurchaseRequisitionEventORM.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _require_event(
    session: Session,
    requisition_id: int,
    event_type: str,
    message: str,
) -> None:
    if not _event_exists(session, requisition_id, event_type):
        raise PurchaseRequisitionConflictError(message)


def _current_import_required(
    session: Session,
    requisition_id: int,
) -> bool:
    event = _latest_event(
        session,
        requisition_id,
        PurchaseRequisitionEventType.FINAL_DESTINATION_SHIPMENT_STARTED,
    )
    if event is None or not isinstance(event.metadata_json, dict):
        raise PurchaseRequisitionConflictError(
            "No existe metadata de importación suficiente para corregir "
            "el estado de destino final."
        )

    value = event.metadata_json.get("import_required")
    if not isinstance(value, bool):
        raise PurchaseRequisitionConflictError(
            "La metadata import_required es inválida o está ausente."
        )
    return value


def administratively_correct_purchase_requisition(
    requisition_id: int,
    target_status: object,
    reason: object,
    comment: object,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    if not can_purchase_requisition_admin_correct(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para corregir administrativamente requisiciones."
        )

    target_session = _session(session)
    requisition = _load(
        requisition_id,
        session=target_session,
    )

    normalized_reason = _required_text(reason, "reason")
    normalized_comment = _required_text(comment, "comment")
    normalized_target = _validate_choice(
        target_status,
        "target_status",
        PurchaseRequisitionStatus.ALL,
    )

    current_status = requisition.status
    allowed_targets = _ADMINISTRATIVE_CORRECTION_TARGETS.get(
        current_status,
        frozenset(),
    )
    if normalized_target not in allowed_targets:
        raise PurchaseRequisitionConflictError(
            "La corrección administrativa solicitada no está permitida "
            f"desde {current_status} hacia {normalized_target}."
        )

    metadata: dict[str, object] = {
        "reason": normalized_reason,
    }

    if current_status == PurchaseRequisitionStatus.NEEDS_INFO:
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType.INFO_REQUESTED,
            "No existe INFO_REQUESTED histórico para revertir.",
        )

    elif current_status == PurchaseRequisitionStatus.REJECTED:
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType.REJECTED,
            "No existe REJECTED histórico para reabrir.",
        )
        requisition.rejected_at = None

    elif current_status == PurchaseRequisitionStatus.IN_QUOTATION:
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType.APPROVED,
            "No existe APPROVED histórico para reabrir revisión.",
        )
        requisition.approved_by_user_id = None
        requisition.approved_at = None
        requisition.approval_comment = None
        metadata["invalidates_operational_effect"] = "APPROVED"

    elif (
        current_status
        == PurchaseRequisitionStatus.QUOTE_PENDING_FINANCE_APPROVAL
    ):
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType
            .QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL,
            "No existe submit financiero histórico para cancelar.",
        )
        quote = _selected_quote_for_requisition(
            target_session,
            requisition.id,
        )
        if (
            quote is None
            or quote.finance_status
            != PurchaseRequisitionQuoteFinanceStatus.PENDING
        ):
            raise PurchaseRequisitionConflictError(
                "No existe una cotización financiera pendiente vigente."
            )
        quote.finance_status = PurchaseRequisitionQuoteFinanceStatus.DRAFT
        quote.finance_submitted_by_user_id = None
        quote.finance_submitted_at = None
        quote.finance_decided_by_user_id = None
        quote.finance_decided_at = None
        quote.finance_comment = None
        metadata["quote_id"] = int(quote.id)
        metadata["cancel_finance_submission"] = True

    elif current_status == PurchaseRequisitionStatus.PAYMENT_REQUESTED:
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType.QUOTE_APPROVED_BY_FINANCE,
            "No existe aprobación financiera histórica para reabrir.",
        )
        quote = _require_approved_selected_quote(
            target_session,
            requisition.id,
        )
        quote.finance_status = PurchaseRequisitionQuoteFinanceStatus.PENDING
        quote.finance_decided_by_user_id = None
        quote.finance_decided_at = None
        quote.finance_comment = None
        metadata["quote_id"] = int(quote.id)
        metadata["reopen_finance_decision"] = True

    elif current_status in {
        PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS,
        PurchaseRequisitionStatus.IMPORT_IN_PROGRESS,
    }:
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType.QUOTE_APPROVED_BY_FINANCE,
            "No existe aprobación financiera histórica para corregir "
            "la logística.",
        )
        _require_approved_selected_quote(
            target_session,
            requisition.id,
        )

    elif (
        current_status
        == PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT
    ):
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType.QUOTE_APPROVED_BY_FINANCE,
            "No existe aprobación financiera histórica para corregir "
            "la logística.",
        )
        _require_approved_selected_quote(
            target_session,
            requisition.id,
        )
        import_required = _current_import_required(
            target_session,
            requisition.id,
        )
        expected_target = (
            PurchaseRequisitionStatus.IMPORT_IN_PROGRESS
            if import_required
            else PurchaseRequisitionStatus.SHIPPING_IN_PROGRESS
        )
        if normalized_target != expected_target:
            raise PurchaseRequisitionConflictError(
                "El target_status no coincide con la decisión auditada "
                "de importación."
            )
        metadata["import_required"] = import_required

    elif current_status == PurchaseRequisitionStatus.RECEIPT_ISSUE:
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType.RECEIPT_ISSUE_REPORTED,
            "No existe incidencia de recepción histórica para revertir.",
        )
        _require_approved_selected_quote(
            target_session,
            requisition.id,
        )
        metadata[
            "invalidate_receipt_issue_operational_effect"
        ] = True

    elif current_status == PurchaseRequisitionStatus.CLOSED:
        _require_event(
            target_session,
            requisition.id,
            PurchaseRequisitionEventType.RECEIVED,
            "No existe RECEIVED histórico para reabrir.",
        )
        _require_approved_selected_quote(
            target_session,
            requisition.id,
        )
        metadata["reopen_after_receipt"] = True
        if normalized_target == PurchaseRequisitionStatus.RECEIPT_ISSUE:
            metadata["target_receipt_issue"] = True

    previous_status = requisition.status
    requisition.status = normalized_target

    _append_event(
        requisition,
        event_type=PurchaseRequisitionEventType.ADMINISTRATIVE_CORRECTION,
        actor_user_id=int(actor.id),
        from_status=previous_status,
        to_status=requisition.status,
        comment=normalized_comment,
        metadata_json=metadata,
    )
    target_session.flush()
    return requisition
