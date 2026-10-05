from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.purchase_requisition import PurchaseRequisitionEventType
from app.services.purchase_requisition_attachment_service import (
    MAX_PURCHASE_REQUISITION_ATTACHMENT_BYTES,
    create_purchase_requisition_attachment,
    get_purchase_requisition_attachment_file,
)
from app.services.purchase_requisition_notification_service import (
    dispatch_event_notifications,
    latest_event_id,
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
    approve_purchase_requisition,
    reject_purchase_requisition,
    request_info_purchase_requisition,
    requester_edit_purchase_requisition,
    resubmit_purchase_requisition,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    assigned_branch_ids,
    can_purchase_requisition_create,
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
        "global_read": has_global_purchase_requisition_read(user),
        "allowed_branch_ids": list(assigned_branch_ids(user)),
        "user": {
            "id": int(user.id),
            "username": user.username,
            "role": user.rol,
        },
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
