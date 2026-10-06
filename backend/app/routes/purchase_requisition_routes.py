from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.purchase_requisition import (
    PurchaseRequisitionEventType,
    PurchaseRequisitionStatus,
)
from app.services.purchase_requisition_attachment_service import (
    MAX_PURCHASE_REQUISITION_ATTACHMENT_BYTES,
    create_purchase_requisition_attachment,
    get_purchase_requisition_attachment_file,
)
from app.services.purchase_requisition_finance_approver_service import (
    create_purchase_requisition_finance_approver,
    list_purchase_requisition_finance_approvers,
    serialize_purchase_requisition_finance_approver,
    update_purchase_requisition_finance_approver,
)
from app.services.purchase_requisition_notification_service import (
    dispatch_event_notifications,
    latest_event_id,
)
from app.services.purchase_requisition_quote_service import (
    create_purchase_requisition_quote,
    select_purchase_requisition_quote,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionNotFoundError,
    PurchaseRequisitionValidationError,
    create_purchase_requisition,
    get_purchase_requisition,
    list_purchase_requisitions,
)
from app.services.purchase_requisition_workflow_service import (
    PurchaseRequisitionConflictError,
    administratively_correct_purchase_requisition,
    advance_purchase_requisition_logistics,
    approve_purchase_requisition,
    approve_purchase_requisition_quote_by_finance,
    confirm_purchase_requisition_receipt,
    reject_purchase_requisition,
    reject_purchase_requisition_quote_by_finance,
    report_purchase_requisition_receipt_issue,
    request_info_purchase_requisition,
    requester_edit_purchase_requisition,
    resume_purchase_requisition_logistics,
    resubmit_purchase_requisition,
    submit_purchase_requisition_quote_for_finance,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    assigned_branch_ids,
    can_purchase_requisition_admin_correct,
    can_purchase_requisition_approve_quote,
    can_purchase_requisition_configure_finance_approvers,
    can_purchase_requisition_confirm_receipt,
    can_purchase_requisition_create,
    can_purchase_requisition_manage_logistics,
    can_purchase_requisition_manage_quotation,
    can_purchase_requisition_review,
    get_current_purchase_requisition_user,
    has_global_purchase_requisition_read,
)


purchase_requisition_bp = Blueprint(
    "purchase_requisition",
    __name__,
)


@purchase_requisition_bp.errorhandler(
    PurchaseRequisitionAuthorizationError
)
def _handle_authorization_error(exc):
    db.session.rollback()
    return jsonify({"mensaje": str(exc)}), 403


@purchase_requisition_bp.errorhandler(
    PurchaseRequisitionValidationError
)
def _handle_validation_error(exc):
    db.session.rollback()
    return jsonify({"mensaje": str(exc)}), 400


@purchase_requisition_bp.errorhandler(
    PurchaseRequisitionNotFoundError
)
def _handle_not_found_error(exc):
    db.session.rollback()
    return jsonify({"mensaje": str(exc)}), 404


@purchase_requisition_bp.errorhandler(
    PurchaseRequisitionConflictError
)
def _handle_conflict_error(exc):
    db.session.rollback()
    return jsonify({"mensaje": str(exc)}), 409


def _current_user():
    return get_current_purchase_requisition_user()


def _dispatch_after_commit(requisition_id: int, event_type: str) -> None:
    try:
        event_id = latest_event_id(requisition_id, event_type)
        if event_id is None:
            current_app.logger.error(
                "Requisición %s sin evento %s para notificación.",
                requisition_id,
                event_type,
            )
            return
        dispatch_event_notifications(event_id)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Falló notificación de requisición %s evento=%s; "
            "la transición de negocio ya estaba confirmada.",
            requisition_id,
            event_type,
        )


@purchase_requisition_bp.get("/access")
@jwt_required()
def get_purchase_requisition_access():
    user = _current_user()
    return jsonify({
        "allowed": True,
        "can_create": can_purchase_requisition_create(user),
        "can_review": can_purchase_requisition_review(user),
        "can_manage_quotation": (
            can_purchase_requisition_manage_quotation(user)
        ),
        "can_approve_requisition_quote": (
            can_purchase_requisition_approve_quote(user)
        ),
        "can_manage_requisition_logistics": (
            can_purchase_requisition_manage_logistics(user)
        ),
        "can_confirm_receipt": (
            can_purchase_requisition_confirm_receipt(user)
        ),
        "can_admin_correct_requisition": (
            can_purchase_requisition_admin_correct(user)
        ),
        "can_configure_finance_approvers": (
            can_purchase_requisition_configure_finance_approvers(user)
        ),
        "global_read": has_global_purchase_requisition_read(user),
        "allowed_branch_ids": list(assigned_branch_ids(user)),
        "user": {
            "id": int(user.id),
            "username": user.username,
            "role": user.rol,
        },
    }), 200


@purchase_requisition_bp.get("/config/finance-approvers")
@jwt_required()
def get_purchase_requisition_finance_approvers():
    actor = _current_user()
    payload = list_purchase_requisition_finance_approvers(actor)
    return jsonify(payload), 200


@purchase_requisition_bp.post("/config/finance-approvers")
@jwt_required()
def post_purchase_requisition_finance_approver():
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    row = create_purchase_requisition_finance_approver(
        payload,
        actor,
    )
    db.session.commit()

    return jsonify({
        "approver": serialize_purchase_requisition_finance_approver(row)
    }), 201


@purchase_requisition_bp.put(
    "/config/finance-approvers/<int:user_id>"
)
@jwt_required()
def put_purchase_requisition_finance_approver(user_id: int):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    row = update_purchase_requisition_finance_approver(
        user_id,
        payload,
        actor,
    )
    db.session.commit()

    return jsonify({
        "approver": serialize_purchase_requisition_finance_approver(row)
    }), 200


@purchase_requisition_bp.post("")
@jwt_required()
def post_purchase_requisition():
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        requisition = create_purchase_requisition(
            payload,
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.CREATED,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_items=True,
            include_events=True,
        )
    }), 201


@purchase_requisition_bp.get("")
@jwt_required()
def get_purchase_requisitions():
    actor = _current_user()
    rows = list_purchase_requisitions(
        actor,
        status=request.args.get("status"),
        branch_id=request.args.get("sucursal_id"),
        priority=request.args.get("priority"),
        date_from=request.args.get("date_from"),
        date_to=request.args.get("date_to"),
    )
    return jsonify({
        "rows": [
            row.to_dict(include_items=True)
            for row in rows
        ],
        "count": len(rows),
    }), 200


@purchase_requisition_bp.get("/<int:requisition_id>")
@jwt_required()
def get_purchase_requisition_detail(requisition_id: int):
    actor = _current_user()
    requisition = get_purchase_requisition(
        requisition_id,
        actor,
    )
    return jsonify({
        "requisition": requisition.to_dict(
            include_items=True,
            include_events=True,
            include_attachments=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/quotes"
)
@jwt_required()
def post_purchase_requisition_quote(requisition_id: int):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        quote = create_purchase_requisition_quote(
            requisition_id,
            payload,
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    return jsonify({
        "quote": quote.to_dict(),
    }), 201


@purchase_requisition_bp.post(
    "/<int:requisition_id>/quotes/<int:quote_id>/select"
)
@jwt_required()
def post_purchase_requisition_quote_select(
    requisition_id: int,
    quote_id: int,
):
    actor = _current_user()

    try:
        quote = select_purchase_requisition_quote(
            requisition_id,
            quote_id,
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    return jsonify({
        "quote": quote.to_dict(),
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/submit-quote-for-finance"
)
@jwt_required()
def post_purchase_requisition_submit_quote_for_finance(
    requisition_id: int,
):
    actor = _current_user()

    try:
        requisition = submit_purchase_requisition_quote_for_finance(
            requisition_id,
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        (
            PurchaseRequisitionEventType
            .QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL
        ),
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_events=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/finance/approve-quote"
)
@jwt_required()
def post_purchase_requisition_finance_approve_quote(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        requisition = approve_purchase_requisition_quote_by_finance(
            requisition_id,
            actor,
            comment=payload.get("comment"),
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.QUOTE_APPROVED_BY_FINANCE,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_events=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/finance/reject-quote"
)
@jwt_required()
def post_purchase_requisition_finance_reject_quote(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        requisition = reject_purchase_requisition_quote_by_finance(
            requisition_id,
            payload.get("reason"),
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.QUOTE_REJECTED_BY_FINANCE,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_events=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/advance-logistics"
)
@jwt_required()
def post_purchase_requisition_advance_logistics(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        requisition = advance_purchase_requisition_logistics(
            requisition_id,
            payload.get("target_status"),
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    if (
        requisition.status
        == PurchaseRequisitionStatus.FINAL_DESTINATION_SHIPMENT
    ):
        _dispatch_after_commit(
            requisition.id,
            (
                PurchaseRequisitionEventType
                .FINAL_DESTINATION_SHIPMENT_STARTED
            ),
        )

    return jsonify({
        "requisition": requisition.to_dict(
            include_events=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/confirm-receipt"
)
@jwt_required()
def post_purchase_requisition_confirm_receipt(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        requisition = confirm_purchase_requisition_receipt(
            requisition_id,
            actor,
            comment=payload.get("comment"),
            evidence_attachment_ids=payload.get(
                "evidence_attachment_ids"
            ),
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.RECEIVED,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_events=True,
            include_attachments=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/report-receipt-issue"
)
@jwt_required()
def post_purchase_requisition_report_receipt_issue(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        requisition = report_purchase_requisition_receipt_issue(
            requisition_id,
            payload.get("issue_type"),
            payload.get("comment"),
            payload.get("evidence_attachment_ids"),
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.RECEIPT_ISSUE_REPORTED,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_events=True,
            include_attachments=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/resume-logistics"
)
@jwt_required()
def post_purchase_requisition_resume_logistics(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        requisition = resume_purchase_requisition_logistics(
            requisition_id,
            payload.get("comment"),
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    return jsonify({
        "requisition": requisition.to_dict(
            include_events=True,
            include_attachments=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/administrative-correction"
)
@jwt_required()
def post_purchase_requisition_administrative_correction(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}

    try:
        requisition = administratively_correct_purchase_requisition(
            requisition_id,
            payload.get("target_status"),
            payload.get("reason"),
            payload.get("comment"),
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.ADMINISTRATIVE_CORRECTION,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_events=True,
            include_attachments=True,
            include_quotes=True,
        )
    }), 200


@purchase_requisition_bp.put(
    "/<int:requisition_id>/requester-edit"
)
@jwt_required()
def put_purchase_requisition_requester_edit(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}
    try:
        requisition = requester_edit_purchase_requisition(
            requisition_id,
            payload,
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    return jsonify({
        "requisition": requisition.to_dict(
            include_items=True,
            include_events=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/request-info"
)
@jwt_required()
def post_purchase_requisition_request_info(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}
    try:
        requisition = request_info_purchase_requisition(
            requisition_id,
            payload.get("comment"),
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.INFO_REQUESTED,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_items=True,
            include_events=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/resubmit"
)
@jwt_required()
def post_purchase_requisition_resubmit(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}
    try:
        requisition = resubmit_purchase_requisition(
            requisition_id,
            actor,
            comment=payload.get("comment"),
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.RESUBMITTED,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_items=True,
            include_events=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/approve"
)
@jwt_required()
def post_purchase_requisition_approve(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}
    try:
        requisition = approve_purchase_requisition(
            requisition_id,
            actor,
            comment=payload.get("comment"),
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.APPROVED,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_items=True,
            include_events=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/reject"
)
@jwt_required()
def post_purchase_requisition_reject(
    requisition_id: int,
):
    actor = _current_user()
    payload = request.get_json(silent=True) or {}
    try:
        requisition = reject_purchase_requisition(
            requisition_id,
            payload.get("reason"),
            actor,
        )
        db.session.commit()
    except (
        PurchaseRequisitionAuthorizationError,
        PurchaseRequisitionValidationError,
        PurchaseRequisitionNotFoundError,
        PurchaseRequisitionConflictError,
    ):
        db.session.rollback()
        raise

    _dispatch_after_commit(
        requisition.id,
        PurchaseRequisitionEventType.REJECTED,
    )

    return jsonify({
        "requisition": requisition.to_dict(
            include_items=True,
            include_events=True,
        )
    }), 200


@purchase_requisition_bp.post(
    "/<int:requisition_id>/attachments"
)
@jwt_required()
def post_purchase_requisition_attachment(
    requisition_id: int,
):
    actor = _current_user()
    uploaded = request.files.get("file")
    if uploaded is None:
        raise PurchaseRequisitionValidationError(
            "file es obligatorio."
        )

    content = uploaded.read(
        MAX_PURCHASE_REQUISITION_ATTACHMENT_BYTES + 1
    )
    if len(content) > MAX_PURCHASE_REQUISITION_ATTACHMENT_BYTES:
        raise PurchaseRequisitionValidationError(
            "El archivo excede el límite máximo de 15 MB."
        )

    attachment = create_purchase_requisition_attachment(
        requisition_id=requisition_id,
        attachment_type=request.form.get(
            "attachment_type",
            "EVIDENCE",
        ),
        content=content,
        original_filename=uploaded.filename or "",
        declared_mime_type=uploaded.mimetype,
        actor=actor,
    )
    return jsonify({
        "attachment": attachment.to_dict(),
    }), 201


@purchase_requisition_bp.get(
    "/<int:requisition_id>/attachments/"
    "<int:attachment_id>/file"
)
@jwt_required()
def get_purchase_requisition_attachment(
    requisition_id: int,
    attachment_id: int,
):
    actor = _current_user()
    attachment, path = (
        get_purchase_requisition_attachment_file(
            requisition_id=requisition_id,
            attachment_id=attachment_id,
            actor=actor,
        )
    )
    return send_file(
        path,
        mimetype=attachment.mime_type,
        as_attachment=True,
        download_name=attachment.original_filename,
        conditional=True,
    )
