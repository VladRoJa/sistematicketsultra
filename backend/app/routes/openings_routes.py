#   backend\app\routes\openings_routes.py


from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    OpeningAuditAction,
    OpeningAuditLogORM,
    OpeningDependencyType,
    OpeningORM,
    OpeningPhaseORM,
    OpeningPhaseStatus,
    OpeningStatus,
    OpeningTaskCommentORM,
    OpeningTaskDependencyORM,
    OpeningTaskORM,
    OpeningTaskPriority,
    OpeningTaskStatus,
    Sucursal,
    SucursalOperationalStatus,
    OpeningTaskDocumentLinkORM,
    OpeningTaskBlockerImpact,
    OpeningTaskBlockerORM,
    OpeningTaskBlockerStatus,
    OpeningTaskBlockerType,
)
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
    WarehouseDocumentUploadError,
    WarehouseDocumentValidationError,
)



openings_bp = Blueprint("openings_bp", __name__)


OPENINGS_ADMIN_ROLES = {
    "ADMIN",
    "ADMINISTRADOR",
    "SUPER_ADMIN",
    "SISTEMAS",
    "APERTURAS_ADMIN",
}

OPENINGS_READ_ROLES = {
    *OPENINGS_ADMIN_ROLES,
    "APERTURAS_MANAGER",
    "APERTURAS_COLABORADOR",
    "APERTURAS_FINANZAS",
    "APERTURAS_LECTOR",
    "GERENTE_REGIONAL",
    "LECTOR_GLOBAL",
}


def _current_role() -> str:
    claims = get_jwt()
    return str(claims.get("rol") or claims.get("role") or "").strip().upper()


def _current_user_id() -> int | None:
    claims = get_jwt()
    raw_user_id = (
        claims.get("user_id")
        or claims.get("id")
        or claims.get("sub_id")
        or get_jwt_identity()
    )

    try:
        return int(raw_user_id)
    except (TypeError, ValueError):
        return None


def _require_openings_read() -> tuple[dict[str, Any], int] | None:
    role = _current_role()

    if role not in OPENINGS_READ_ROLES:
        return jsonify({
            "error": "Forbidden",
            "detail": "No autorizado para consultar Aperturas.",
        }), 403

    return None


def _require_openings_admin() -> tuple[dict[str, Any], int] | None:
    role = _current_role()

    if role not in OPENINGS_ADMIN_ROLES:
        return jsonify({
            "error": "Forbidden",
            "detail": "No autorizado para administrar Aperturas.",
        }), 403

    return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def _parse_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None

    return Decimal(str(value))

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _serialize_decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None

    return float(value)


def _serialize_date(value: date | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _serialize_user(user: Any) -> dict[str, Any] | None:
    if not user:
        return None

    return {
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
        "rol": getattr(user, "rol", None),
    }


def _serialize_sucursal(sucursal: Sucursal | None) -> dict[str, Any] | None:
    if not sucursal:
        return None

    return {
        "sucursal_id": sucursal.sucursal_id,
        "sucursal": sucursal.sucursal,
        "serie": sucursal.serie,
        "estado": sucursal.estado,
        "municipio": sucursal.municipio,
        "direccion": sucursal.direccion,
        "operational_status": sucursal.operational_status,
    }


def _serialize_opening(opening: OpeningORM) -> dict[str, Any]:
    return {
        "id": opening.id,
        "sucursal_id": opening.sucursal_id,
        "sucursal": _serialize_sucursal(opening.sucursal),
        "opening_key": opening.opening_key,
        "name": opening.name,
        "description": opening.description,
        "status": opening.status,
        "planned_start_date": _serialize_date(opening.planned_start_date),
        "target_opening_date": _serialize_date(opening.target_opening_date),
        "actual_opening_date": _serialize_date(opening.actual_opening_date),
        "general_owner_user_id": opening.general_owner_user_id,
        "general_owner_user": _serialize_user(opening.general_owner_user),
        "budget_authorized_total": _serialize_decimal(opening.budget_authorized_total),
        "budget_currency_code": opening.budget_currency_code,
        "created_by": opening.created_by,
        "updated_by": opening.updated_by,
        "created_at": _serialize_datetime(opening.created_at),
        "updated_at": _serialize_datetime(opening.updated_at),
    }

def _serialize_department(department: Any) -> dict[str, Any] | None:
    if not department:
        return None

    return {
        "id": getattr(department, "id", None),
        "nombre": getattr(department, "nombre", None),
    }


def _serialize_phase(phase: OpeningPhaseORM) -> dict[str, Any]:
    return {
        "id": phase.id,
        "opening_id": phase.opening_id,
        "name": phase.name,
        "description": phase.description,
        "sort_order": phase.sort_order,
        "planned_start_date": _serialize_date(phase.planned_start_date),
        "planned_end_date": _serialize_date(phase.planned_end_date),
        "actual_start_date": _serialize_date(phase.actual_start_date),
        "actual_end_date": _serialize_date(phase.actual_end_date),
        "status": phase.status,
        "owner_department_id": phase.owner_department_id,
        "owner_department": _serialize_department(phase.owner_department),
        "owner_user_id": phase.owner_user_id,
        "owner_user": _serialize_user(phase.owner_user),
        "progress_percent": _serialize_decimal(phase.progress_percent),
        "created_by": phase.created_by,
        "updated_by": phase.updated_by,
        "created_at": _serialize_datetime(phase.created_at),
        "updated_at": _serialize_datetime(phase.updated_at),
    }

def _serialize_task(task: OpeningTaskORM) -> dict[str, Any]:
    return {
        "id": task.id,
        "opening_id": task.opening_id,
        "phase_id": task.phase_id,
        "phase": _serialize_phase(task.phase) if task.phase else None,
        "parent_task_id": task.parent_task_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "owner_user_id": task.owner_user_id,
        "owner_user": _serialize_user(task.owner_user),
        "owner_department_id": task.owner_department_id,
        "owner_department": _serialize_department(task.owner_department),
        "planned_start_date": _serialize_date(task.planned_start_date),
        "planned_due_date": _serialize_date(task.planned_due_date),
        "actual_start_date": _serialize_date(task.actual_start_date),
        "actual_completed_at": _serialize_datetime(task.actual_completed_at),
        "progress_percent": _serialize_decimal(task.progress_percent),
        "sort_order": task.sort_order,
        "requires_document": bool(task.requires_document),
        "requires_payment": bool(task.requires_payment),
        "created_by": task.created_by,
        "updated_by": task.updated_by,
        "created_at": _serialize_datetime(task.created_at),
        "updated_at": _serialize_datetime(task.updated_at),
    }

def _serialize_task_dependency(
    dependency: OpeningTaskDependencyORM,
) -> dict[str, Any]:
    return {
        "id": dependency.id,
        "task_id": dependency.task_id,
        "depends_on_task_id": dependency.depends_on_task_id,
        "dependency_type": dependency.dependency_type,
        "task": {
            "id": dependency.task.id,
            "title": dependency.task.title,
            "status": dependency.task.status,
        } if dependency.task else None,
        "depends_on_task": {
            "id": dependency.depends_on_task.id,
            "title": dependency.depends_on_task.title,
            "status": dependency.depends_on_task.status,
        } if dependency.depends_on_task else None,
        "created_by": dependency.created_by,
        "created_at": _serialize_datetime(dependency.created_at),
    }

def _serialize_task_comment(comment: OpeningTaskCommentORM) -> dict[str, Any]:
    return {
        "id": comment.id,
        "opening_id": comment.opening_id,
        "task_id": comment.task_id,
        "comment": comment.comment,
        "is_system_event": bool(comment.is_system_event),
        "created_by": comment.created_by,
        "creator": _serialize_user(comment.creator),
        "created_at": _serialize_datetime(comment.created_at),
    }

def _serialize_task_document_link(link: OpeningTaskDocumentLinkORM) -> dict[str, Any]:
    upload = link.warehouse_upload

    return {
        "id": link.id,
        "opening_id": link.opening_id,
        "task_id": link.task_id,
        "warehouse_upload_id": link.warehouse_upload_id,
        "document_role": link.document_role,
        "notes": link.notes,
        "status": link.status,
        "linked_by": link.linked_by,
        "linked_by_user": _serialize_user(link.linker),
        "linked_at": _serialize_datetime(link.linked_at),
        "unlinked_by": link.unlinked_by,
        "unlinked_by_user": _serialize_user(link.unlinker),
        "unlinked_at": _serialize_datetime(link.unlinked_at),
        "upload": {
            "id": upload.id,
            "original_filename": upload.original_filename,
            "stored_filename": upload.stored_filename,
            "file_size_bytes": upload.file_size_bytes,
            "file_hash_sha256": upload.file_hash_sha256,
            "mime_type": upload.mime_type,
            "extension": upload.extension,
            "status": upload.status,
            "report_type_key": upload.report_type.key if upload.report_type else None,
            "report_type_label": upload.report_type.label if upload.report_type else None,
            "uploaded_by_user_id": upload.uploaded_by_user_id,
            "uploaded_by_username": upload.uploader.username if upload.uploader else None,
            "created_at": _serialize_datetime(upload.created_at),
            "download_url": f"/api/warehouse/uploads/{upload.id}/download",
        } if upload else None,
    }

def _serialize_task_summary(task: OpeningTaskORM | None) -> dict[str, Any] | None:
    if not task:
        return None

    return {
        "id": task.id,
        "opening_id": task.opening_id,
        "phase_id": task.phase_id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "planned_start_date": _serialize_date(task.planned_start_date),
        "planned_due_date": _serialize_date(task.planned_due_date),
        "progress_percent": _serialize_decimal(task.progress_percent),
    }


def _serialize_task_blocker(blocker: OpeningTaskBlockerORM) -> dict[str, Any]:
    return {
        "id": blocker.id,
        "opening_id": blocker.opening_id,
        "blocked_task_id": blocker.blocked_task_id,
        "blocked_task": _serialize_task_summary(blocker.blocked_task),
        "blocker_type": blocker.blocker_type,
        "blocking_task_id": blocker.blocking_task_id,
        "blocking_task": _serialize_task_summary(blocker.blocking_task),
        "reason": blocker.reason,
        "impact_level": blocker.impact_level,
        "status": blocker.status,
        "created_by": blocker.created_by,
        "creator": _serialize_user(blocker.creator),
        "resolved_by": blocker.resolved_by,
        "resolver": _serialize_user(blocker.resolver),
        "created_at": _serialize_datetime(blocker.created_at),
        "resolved_at": _serialize_datetime(blocker.resolved_at),
        "resolution_comment": blocker.resolution_comment,
    }

def _safe_json_int(payload: dict[str, Any] | None, key: str) -> int | None:
    if not payload:
        return None

    value = payload.get(key)

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_json_text(payload: dict[str, Any] | None, key: str) -> str | None:
    if not payload:
        return None

    value = payload.get(key)

    if value is None:
        return None

    return str(value)


def _audit_log_belongs_to_task(audit_log: OpeningAuditLogORM, task_id: int) -> bool:
    if audit_log.entity_type == "TASK" and audit_log.entity_id == task_id:
        return True

    payloads = (
        audit_log.metadata_json or {},
        audit_log.old_value_json or {},
        audit_log.new_value_json or {},
    )

    task_keys = (
        "task_id",
        "blocked_task_id",
        "blocking_task_id",
        "depends_on_task_id",
    )

    for payload in payloads:
        for key in task_keys:
            if _safe_json_int(payload, key) == task_id:
                return True

    return False


def _build_task_audit_timeline_event(audit_log: OpeningAuditLogORM) -> dict[str, Any]:
    old_value = audit_log.old_value_json or {}
    new_value = audit_log.new_value_json or {}
    metadata = audit_log.metadata_json or {}

    title = "Actualización"
    description = "Se registró un movimiento en la tarea."
    event_type = "AUDIT"

    if audit_log.action == OpeningAuditAction.TASK_CREATED:
        title = "Tarea creada"
        description = _safe_json_text(new_value, "title") or "Se creó la tarea."

    elif audit_log.action == OpeningAuditAction.TASK_UPDATED:
        title = "Tarea actualizada"
        description = "Se actualizaron datos generales de la tarea."

    elif audit_log.action == OpeningAuditAction.TASK_STATUS_CHANGED:
        title = "Estado actualizado"
        old_status = _safe_json_text(old_value, "status") or "Sin estado"
        new_status = _safe_json_text(new_value, "status") or "Sin estado"
        description = f"{old_status} → {new_status}"

    elif audit_log.action == OpeningAuditAction.TASK_DUE_DATE_CHANGED:
        title = "Fecha compromiso actualizada"
        old_due_date = _safe_json_text(old_value, "planned_due_date") or "Sin fecha"
        new_due_date = _safe_json_text(new_value, "planned_due_date") or "Sin fecha"
        description = f"{old_due_date} → {new_due_date}"

    elif audit_log.action == OpeningAuditAction.TASK_OWNER_CHANGED:
        title = "Responsable actualizado"
        old_owner = _safe_json_text(old_value, "owner_user_id") or "Sin responsable"
        new_owner = _safe_json_text(new_value, "owner_user_id") or "Sin responsable"
        description = f"{old_owner} → {new_owner}"

    elif audit_log.action == OpeningAuditAction.TASK_DEPENDENCY_CREATED:
        event_type = "DEPENDENCY"
        title = "Dependencia agregada"
        depends_on_title = None

        depends_on_task = new_value.get("depends_on_task") if isinstance(new_value, dict) else None
        if isinstance(depends_on_task, dict):
            depends_on_title = depends_on_task.get("title")

        description = f"Depende de: {depends_on_title or metadata.get('depends_on_task_id') or 'tarea'}"

    elif audit_log.action == OpeningAuditAction.TASK_DEPENDENCY_DELETED:
        event_type = "DEPENDENCY"
        title = "Dependencia eliminada"
        depends_on_title = None

        depends_on_task = old_value.get("depends_on_task") if isinstance(old_value, dict) else None
        if isinstance(depends_on_task, dict):
            depends_on_title = depends_on_task.get("title")

        description = f"Se eliminó dependencia con: {depends_on_title or metadata.get('depends_on_task_id') or 'tarea'}"

    elif audit_log.action == OpeningAuditAction.TASK_BLOCKER_CREATED:
        event_type = "BLOCKER"
        title = "Bloqueo creado"

        blocker_type = _safe_json_text(new_value, "blocker_type") or "OTHER"
        impact_level = _safe_json_text(new_value, "impact_level") or "MEDIUM"
        reason = _safe_json_text(new_value, "reason") or "Sin motivo capturado."

        description = f"{blocker_type} · {impact_level} · {reason}"

    elif audit_log.action == OpeningAuditAction.TASK_BLOCKER_RESOLVED:
        event_type = "BLOCKER"
        title = "Bloqueo resuelto"

        resolution_comment = (
            _safe_json_text(new_value, "resolution_comment")
            or "Sin comentario de resolución."
        )

        description = resolution_comment

    return {
        "id": f"audit-{audit_log.id}",
        "source": "AUDIT",
        "event_type": event_type,
        "action": audit_log.action,
        "title": title,
        "description": description,
        "created_at": _serialize_datetime(audit_log.created_at),
        "actor": _serialize_user(audit_log.actor_user),
        "entity_type": audit_log.entity_type,
        "entity_id": audit_log.entity_id,
        "old_value_json": old_value or None,
        "new_value_json": new_value or None,
        "metadata_json": metadata or None,
    }


def _build_task_comment_timeline_event(comment: OpeningTaskCommentORM) -> dict[str, Any]:
    return {
        "id": f"comment-{comment.id}",
        "source": "COMMENT",
        "event_type": "COMMENT",
        "action": "TASK_COMMENT_CREATED",
        "title": "Comentario agregado",
        "description": comment.comment,
        "created_at": _serialize_datetime(comment.created_at),
        "actor": _serialize_user(comment.creator),
        "entity_type": "TASK_COMMENT",
        "entity_id": comment.id,
        "old_value_json": None,
        "new_value_json": _serialize_task_comment(comment),
        "metadata_json": {
            "task_id": comment.task_id,
            "is_system_event": bool(comment.is_system_event),
        },
    }

def _audit_opening(
    opening_id: int,
    action: str,
    *,
    entity_type: str = "OPENING",
    entity_id: int | None = None,
    old_value_json: dict[str, Any] | None = None,
    new_value_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    db.session.add(
        OpeningAuditLogORM(
            opening_id=opening_id,
            entity_type=entity_type,
            entity_id=entity_id or opening_id,
            action=action,
            old_value_json=old_value_json,
            new_value_json=new_value_json,
            metadata_json=metadata_json,
            actor_user_id=_current_user_id(),
        )
    )


@openings_bp.route("", methods=["GET"])
@jwt_required()
def list_openings():
    denied = _require_openings_read()
    if denied:
        return denied

    status = (request.args.get("status") or "").strip().upper()
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", default=1, type=int) or 1
    page_size = request.args.get("page_size", default=25, type=int) or 25

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    query = OpeningORM.query

    if status and status != "ALL":
        query = query.filter(OpeningORM.status == status)

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                OpeningORM.opening_key.ilike(like),
                OpeningORM.name.ilike(like),
                OpeningORM.description.ilike(like),
            )
        )

    query = query.order_by(
        OpeningORM.target_opening_date.asc().nullslast(),
        OpeningORM.created_at.desc(),
    )

    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [_serialize_opening(item) for item in pagination.items],
        "page": pagination.page,
        "page_size": pagination.per_page,
        "total": pagination.total,
        "total_pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }), 200


@openings_bp.route("", methods=["POST"])
@jwt_required()
def create_opening():
    denied = _require_openings_admin()
    if denied:
        return denied

    data = request.get_json(silent=True) or {}

    required_fields = ["sucursal_id", "opening_key", "name"]
    missing = [field for field in required_fields if not data.get(field)]

    if missing:
        return jsonify({
            "error": "Bad Request",
            "detail": "Campos requeridos incompletos.",
            "missing": missing,
        }), 400

    try:
        sucursal_id = int(data["sucursal_id"])
    except (TypeError, ValueError):
        return jsonify({
            "error": "Bad Request",
            "detail": "sucursal_id debe ser entero.",
        }), 400

    sucursal = db.session.get(Sucursal, sucursal_id)

    if not sucursal:
        return jsonify({
            "error": "Not Found",
            "detail": "Sucursal no encontrada.",
        }), 404

    opening_key = str(data["opening_key"]).strip().upper()
    name = str(data["name"]).strip()

    if not opening_key or not name:
        return jsonify({
            "error": "Bad Request",
            "detail": "opening_key y name son obligatorios.",
        }), 400

    try:
        opening = OpeningORM(
            sucursal_id=sucursal_id,
            opening_key=opening_key,
            name=name,
            description=(str(data.get("description")).strip() if data.get("description") else None),
            status=str(data.get("status") or OpeningStatus.DRAFT).strip().upper(),
            planned_start_date=_parse_date(data.get("planned_start_date")),
            target_opening_date=_parse_date(data.get("target_opening_date")),
            actual_opening_date=_parse_date(data.get("actual_opening_date")),
            general_owner_user_id=data.get("general_owner_user_id"),
            budget_authorized_total=_parse_decimal(data.get("budget_authorized_total")),
            budget_currency_code=str(data.get("budget_currency_code") or "MXN").strip().upper(),
            created_by=_current_user_id(),
            updated_by=_current_user_id(),
        )

        if opening.status not in OpeningStatus.ALL:
            return jsonify({
                "error": "Bad Request",
                "detail": "Estado de apertura inválido.",
                "allowed": list(OpeningStatus.ALL),
            }), 400

        db.session.add(opening)
        db.session.flush()

        if sucursal.operational_status != SucursalOperationalStatus.EN_APERTURA:
            sucursal.operational_status = SucursalOperationalStatus.EN_APERTURA

        _audit_opening(
            opening.id,
            OpeningAuditAction.OPENING_CREATED,
            new_value_json=_serialize_opening(opening),
        )

        db.session.commit()

        return jsonify({
            "message": "Apertura creada.",
            "item": _serialize_opening(opening),
        }), 201

    except ValueError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "Conflict",
            "detail": "Ya existe una apertura con esa clave.",
        }), 409


@openings_bp.route("/<int:opening_id>", methods=["GET"])
@jwt_required()
def get_opening(opening_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    return jsonify({
        "item": _serialize_opening(opening),
    }), 200


@openings_bp.route("/<int:opening_id>", methods=["PATCH"])
@jwt_required()
def update_opening(opening_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    data = request.get_json(silent=True) or {}

    old_value = _serialize_opening(opening)

    try:
        if "name" in data:
            opening.name = str(data.get("name") or "").strip()

        if "description" in data:
            opening.description = (
                str(data.get("description")).strip()
                if data.get("description")
                else None
            )

        if "status" in data:
            next_status = str(data.get("status") or "").strip().upper()

            if next_status not in OpeningStatus.ALL:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "Estado de apertura inválido.",
                    "allowed": list(OpeningStatus.ALL),
                }), 400

            opening.status = next_status

        if "planned_start_date" in data:
            opening.planned_start_date = _parse_date(data.get("planned_start_date"))

        if "target_opening_date" in data:
            opening.target_opening_date = _parse_date(data.get("target_opening_date"))

        if "actual_opening_date" in data:
            opening.actual_opening_date = _parse_date(data.get("actual_opening_date"))

        if "general_owner_user_id" in data:
            opening.general_owner_user_id = data.get("general_owner_user_id")

        if "budget_authorized_total" in data:
            opening.budget_authorized_total = _parse_decimal(data.get("budget_authorized_total"))

        if "budget_currency_code" in data:
            opening.budget_currency_code = str(
                data.get("budget_currency_code") or "MXN"
            ).strip().upper()

        opening.updated_by = _current_user_id()

        _audit_opening(
            opening.id,
            OpeningAuditAction.OPENING_UPDATED,
            old_value_json=old_value,
            new_value_json=_serialize_opening(opening),
        )

        db.session.commit()

        return jsonify({
            "message": "Apertura actualizada.",
            "item": _serialize_opening(opening),
        }), 200

    except ValueError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400
        
@openings_bp.route("/<int:opening_id>/phases", methods=["GET"])
@jwt_required()
def list_opening_phases(opening_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    phases = (
        OpeningPhaseORM.query
        .filter(OpeningPhaseORM.opening_id == opening_id)
        .order_by(OpeningPhaseORM.sort_order.asc(), OpeningPhaseORM.id.asc())
        .all()
    )

    return jsonify({
        "items": [_serialize_phase(phase) for phase in phases],
    }), 200


@openings_bp.route("/<int:opening_id>/phases", methods=["POST"])
@jwt_required()
def create_opening_phase(opening_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    data = request.get_json(silent=True) or {}

    name = str(data.get("name") or "").strip()

    if not name:
        return jsonify({
            "error": "Bad Request",
            "detail": "El nombre de la fase es obligatorio.",
        }), 400

    status = str(
        data.get("status") or OpeningPhaseStatus.NOT_STARTED
    ).strip().upper()

    if status not in OpeningPhaseStatus.ALL:
        return jsonify({
            "error": "Bad Request",
            "detail": "Estado de fase inválido.",
            "allowed": list(OpeningPhaseStatus.ALL),
        }), 400

    try:
        phase = OpeningPhaseORM(
            opening_id=opening_id,
            name=name,
            description=(
                str(data.get("description")).strip()
                if data.get("description")
                else None
            ),
            sort_order=int(data.get("sort_order") or 0),
            planned_start_date=_parse_date(data.get("planned_start_date")),
            planned_end_date=_parse_date(data.get("planned_end_date")),
            actual_start_date=_parse_date(data.get("actual_start_date")),
            actual_end_date=_parse_date(data.get("actual_end_date")),
            status=status,
            owner_department_id=data.get("owner_department_id"),
            owner_user_id=data.get("owner_user_id"),
            progress_percent=_parse_decimal(data.get("progress_percent")) or Decimal("0"),
            created_by=_current_user_id(),
            updated_by=_current_user_id(),
        )

        db.session.add(phase)
        db.session.flush()

        _audit_opening(
            opening_id,
            OpeningAuditAction.PHASE_CREATED,
            entity_type="PHASE",
            entity_id=phase.id,
            new_value_json=_serialize_phase(phase),
        )

        db.session.commit()

        return jsonify({
            "message": "Fase creada.",
            "item": _serialize_phase(phase),
        }), 201

    except ValueError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "Conflict",
            "detail": "Ya existe una fase con ese nombre para esta apertura.",
        }), 409


@openings_bp.route("/<int:opening_id>/phases/<int:phase_id>", methods=["PATCH"])
@jwt_required()
def update_opening_phase(opening_id: int, phase_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    phase = db.session.get(OpeningPhaseORM, phase_id)

    if not phase or phase.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Fase no encontrada para esta apertura.",
        }), 404

    data = request.get_json(silent=True) or {}
    old_value = _serialize_phase(phase)

    try:
        if "name" in data:
            phase.name = str(data.get("name") or "").strip()

            if not phase.name:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "El nombre de la fase no puede quedar vacío.",
                }), 400

        if "description" in data:
            phase.description = (
                str(data.get("description")).strip()
                if data.get("description")
                else None
            )

        if "sort_order" in data:
            phase.sort_order = int(data.get("sort_order") or 0)

        if "planned_start_date" in data:
            phase.planned_start_date = _parse_date(data.get("planned_start_date"))

        if "planned_end_date" in data:
            phase.planned_end_date = _parse_date(data.get("planned_end_date"))

        if "actual_start_date" in data:
            phase.actual_start_date = _parse_date(data.get("actual_start_date"))

        if "actual_end_date" in data:
            phase.actual_end_date = _parse_date(data.get("actual_end_date"))

        if "status" in data:
            next_status = str(data.get("status") or "").strip().upper()

            if next_status not in OpeningPhaseStatus.ALL:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "Estado de fase inválido.",
                    "allowed": list(OpeningPhaseStatus.ALL),
                }), 400

            phase.status = next_status

        if "owner_department_id" in data:
            phase.owner_department_id = data.get("owner_department_id")

        if "owner_user_id" in data:
            phase.owner_user_id = data.get("owner_user_id")

        if "progress_percent" in data:
            next_progress = _parse_decimal(data.get("progress_percent")) or Decimal("0")

            if next_progress < 0 or next_progress > 100:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "El avance debe estar entre 0 y 100.",
                }), 400

            phase.progress_percent = next_progress

        phase.updated_by = _current_user_id()

        _audit_opening(
            opening_id,
            OpeningAuditAction.PHASE_UPDATED,
            entity_type="PHASE",
            entity_id=phase.id,
            old_value_json=old_value,
            new_value_json=_serialize_phase(phase),
        )

        db.session.commit()

        return jsonify({
            "message": "Fase actualizada.",
            "item": _serialize_phase(phase),
        }), 200

    except ValueError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "Conflict",
            "detail": "Ya existe una fase con ese nombre para esta apertura.",
        }), 409
        
@openings_bp.route("/<int:opening_id>/tasks", methods=["GET"])
@jwt_required()
def list_opening_tasks(opening_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    status = (request.args.get("status") or "").strip().upper()
    phase_id = request.args.get("phase_id", type=int)
    owner_user_id = request.args.get("owner_user_id", type=int)
    q = (request.args.get("q") or "").strip()

    query = OpeningTaskORM.query.filter(OpeningTaskORM.opening_id == opening_id)

    if status and status != "ALL":
        query = query.filter(OpeningTaskORM.status == status)

    if phase_id:
        query = query.filter(OpeningTaskORM.phase_id == phase_id)

    if owner_user_id:
        query = query.filter(OpeningTaskORM.owner_user_id == owner_user_id)

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                OpeningTaskORM.title.ilike(like),
                OpeningTaskORM.description.ilike(like),
            )
        )

    tasks = (
        query
        .order_by(
            OpeningTaskORM.phase_id.asc().nullslast(),
            OpeningTaskORM.sort_order.asc(),
            OpeningTaskORM.id.asc(),
        )
        .all()
    )

    return jsonify({
        "items": [_serialize_task(task) for task in tasks],
    }), 200


@openings_bp.route("/<int:opening_id>/tasks", methods=["POST"])
@jwt_required()
def create_opening_task(opening_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    data = request.get_json(silent=True) or {}

    title = str(data.get("title") or "").strip()

    if not title:
        return jsonify({
            "error": "Bad Request",
            "detail": "El título de la tarea es obligatorio.",
        }), 400

    phase_id = data.get("phase_id")

    if phase_id:
        try:
            phase_id = int(phase_id)
        except (TypeError, ValueError):
            return jsonify({
                "error": "Bad Request",
                "detail": "phase_id debe ser entero.",
            }), 400

        phase = db.session.get(OpeningPhaseORM, phase_id)

        if not phase or phase.opening_id != opening_id:
            return jsonify({
                "error": "Bad Request",
                "detail": "La fase no pertenece a esta apertura.",
            }), 400

    parent_task_id = data.get("parent_task_id")

    if parent_task_id:
        try:
            parent_task_id = int(parent_task_id)
        except (TypeError, ValueError):
            return jsonify({
                "error": "Bad Request",
                "detail": "parent_task_id debe ser entero.",
            }), 400

        parent_task = db.session.get(OpeningTaskORM, parent_task_id)

        if not parent_task or parent_task.opening_id != opening_id:
            return jsonify({
                "error": "Bad Request",
                "detail": "La tarea padre no pertenece a esta apertura.",
            }), 400

    status = str(
        data.get("status") or OpeningTaskStatus.NOT_STARTED
    ).strip().upper()

    if status not in OpeningTaskStatus.ALL:
        return jsonify({
            "error": "Bad Request",
            "detail": "Estado de tarea inválido.",
            "allowed": list(OpeningTaskStatus.ALL),
        }), 400

    priority = str(
        data.get("priority") or OpeningTaskPriority.MEDIUM
    ).strip().upper()

    if priority not in OpeningTaskPriority.ALL:
        return jsonify({
            "error": "Bad Request",
            "detail": "Prioridad de tarea inválida.",
            "allowed": list(OpeningTaskPriority.ALL),
        }), 400

    progress_percent = _parse_decimal(data.get("progress_percent")) or Decimal("0")

    if progress_percent < 0 or progress_percent > 100:
        return jsonify({
            "error": "Bad Request",
            "detail": "El avance debe estar entre 0 y 100.",
        }), 400

    try:
        task = OpeningTaskORM(
            opening_id=opening_id,
            phase_id=phase_id,
            parent_task_id=parent_task_id,
            title=title,
            description=(
                str(data.get("description")).strip()
                if data.get("description")
                else None
            ),
            status=status,
            priority=priority,
            owner_user_id=data.get("owner_user_id"),
            owner_department_id=data.get("owner_department_id"),
            planned_start_date=_parse_date(data.get("planned_start_date")),
            planned_due_date=_parse_date(data.get("planned_due_date")),
            actual_start_date=_parse_date(data.get("actual_start_date")),
            actual_completed_at=_utc_now() if status == OpeningTaskStatus.COMPLETED else None,
            progress_percent=progress_percent,
            sort_order=int(data.get("sort_order") or 0),
            requires_document=bool(data.get("requires_document") or False),
            requires_payment=bool(data.get("requires_payment") or False),
            created_by=_current_user_id(),
            updated_by=_current_user_id(),
        )

        db.session.add(task)
        db.session.flush()

        _audit_opening(
            opening_id,
            OpeningAuditAction.TASK_CREATED,
            entity_type="TASK",
            entity_id=task.id,
            new_value_json=_serialize_task(task),
        )

        db.session.commit()

        return jsonify({
            "message": "Tarea creada.",
            "item": _serialize_task(task),
        }), 201

    except ValueError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400


@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>", methods=["PATCH"])
@jwt_required()
def update_opening_task(opening_id: int, task_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    data = request.get_json(silent=True) or {}
    old_value = _serialize_task(task)

    try:
        if "phase_id" in data:
            phase_id = data.get("phase_id")

            if phase_id in (None, ""):
                task.phase_id = None
            else:
                phase_id = int(phase_id)
                phase = db.session.get(OpeningPhaseORM, phase_id)

                if not phase or phase.opening_id != opening_id:
                    return jsonify({
                        "error": "Bad Request",
                        "detail": "La fase no pertenece a esta apertura.",
                    }), 400

                task.phase_id = phase_id

        if "parent_task_id" in data:
            parent_task_id = data.get("parent_task_id")

            if parent_task_id in (None, ""):
                task.parent_task_id = None
            else:
                parent_task_id = int(parent_task_id)

                if parent_task_id == task.id:
                    return jsonify({
                        "error": "Bad Request",
                        "detail": "Una tarea no puede ser padre de sí misma.",
                    }), 400

                parent_task = db.session.get(OpeningTaskORM, parent_task_id)

                if not parent_task or parent_task.opening_id != opening_id:
                    return jsonify({
                        "error": "Bad Request",
                        "detail": "La tarea padre no pertenece a esta apertura.",
                    }), 400

                task.parent_task_id = parent_task_id

        if "title" in data:
            task.title = str(data.get("title") or "").strip()

            if not task.title:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "El título de la tarea no puede quedar vacío.",
                }), 400

        if "description" in data:
            task.description = (
                str(data.get("description")).strip()
                if data.get("description")
                else None
            )

        if "status" in data:
            next_status = str(data.get("status") or "").strip().upper()

            if next_status not in OpeningTaskStatus.ALL:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "Estado de tarea inválido.",
                    "allowed": list(OpeningTaskStatus.ALL),
                }), 400

            task.status = next_status

            if next_status == OpeningTaskStatus.COMPLETED:
                task.progress_percent = Decimal("100")
                if not task.actual_completed_at:
                    task.actual_completed_at = _utc_now()
            elif task.actual_completed_at and next_status != OpeningTaskStatus.COMPLETED:
                task.actual_completed_at = None

        if "priority" in data:
            next_priority = str(data.get("priority") or "").strip().upper()

            if next_priority not in OpeningTaskPriority.ALL:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "Prioridad de tarea inválida.",
                    "allowed": list(OpeningTaskPriority.ALL),
                }), 400

            task.priority = next_priority

        if "owner_user_id" in data:
            task.owner_user_id = data.get("owner_user_id")

        if "owner_department_id" in data:
            task.owner_department_id = data.get("owner_department_id")

        if "planned_start_date" in data:
            task.planned_start_date = _parse_date(data.get("planned_start_date"))

        if "planned_due_date" in data:
            task.planned_due_date = _parse_date(data.get("planned_due_date"))

        if "actual_start_date" in data:
            task.actual_start_date = _parse_date(data.get("actual_start_date"))

        if "progress_percent" in data:
            next_progress = _parse_decimal(data.get("progress_percent")) or Decimal("0")

            if next_progress < 0 or next_progress > 100:
                return jsonify({
                    "error": "Bad Request",
                    "detail": "El avance debe estar entre 0 y 100.",
                }), 400

            task.progress_percent = next_progress

            if next_progress == 100:
                task.status = OpeningTaskStatus.COMPLETED
                if not task.actual_completed_at:
                    task.actual_completed_at = _utc_now()
            elif task.status == OpeningTaskStatus.COMPLETED:
                task.status = OpeningTaskStatus.IN_PROGRESS
                task.actual_completed_at = None

        if "sort_order" in data:
            task.sort_order = int(data.get("sort_order") or 0)

        if "requires_document" in data:
            task.requires_document = bool(data.get("requires_document"))

        if "requires_payment" in data:
            task.requires_payment = bool(data.get("requires_payment"))

        task.updated_by = _current_user_id()

        action = OpeningAuditAction.TASK_UPDATED

        if old_value.get("status") != task.status:
            action = OpeningAuditAction.TASK_STATUS_CHANGED
        elif old_value.get("planned_due_date") != _serialize_date(task.planned_due_date):
            action = OpeningAuditAction.TASK_DUE_DATE_CHANGED
        elif old_value.get("owner_user_id") != task.owner_user_id:
            action = OpeningAuditAction.TASK_OWNER_CHANGED

        _audit_opening(
            opening_id,
            action,
            entity_type="TASK",
            entity_id=task.id,
            old_value_json=old_value,
            new_value_json=_serialize_task(task),
        )

        db.session.commit()

        return jsonify({
            "message": "Tarea actualizada.",
            "item": _serialize_task(task),
        }), 200

    except ValueError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400
        
@openings_bp.route("/<int:opening_id>/task-dependencies", methods=["GET"])
@jwt_required()
def list_opening_task_dependencies(opening_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    dependencies = (
        OpeningTaskDependencyORM.query
        .join(OpeningTaskORM, OpeningTaskDependencyORM.task_id == OpeningTaskORM.id)
        .filter(OpeningTaskORM.opening_id == opening_id)
        .order_by(
            OpeningTaskDependencyORM.task_id.asc(),
            OpeningTaskDependencyORM.depends_on_task_id.asc(),
        )
        .all()
    )

    return jsonify({
        "items": [
            _serialize_task_dependency(dependency)
            for dependency in dependencies
        ],
    }), 200


@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>/dependencies", methods=["GET"])
@jwt_required()
def list_task_dependencies(opening_id: int, task_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    dependencies = (
        OpeningTaskDependencyORM.query
        .filter(OpeningTaskDependencyORM.task_id == task_id)
        .order_by(OpeningTaskDependencyORM.id.asc())
        .all()
    )

    return jsonify({
        "items": [
            _serialize_task_dependency(dependency)
            for dependency in dependencies
        ],
    }), 200


@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>/dependencies", methods=["POST"])
@jwt_required()
def create_task_dependency(opening_id: int, task_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    data = request.get_json(silent=True) or {}

    depends_on_task_id = data.get("depends_on_task_id")

    if not depends_on_task_id:
        return jsonify({
            "error": "Bad Request",
            "detail": "depends_on_task_id es obligatorio.",
        }), 400

    try:
        depends_on_task_id = int(depends_on_task_id)
    except (TypeError, ValueError):
        return jsonify({
            "error": "Bad Request",
            "detail": "depends_on_task_id debe ser entero.",
        }), 400

    if depends_on_task_id == task_id:
        return jsonify({
            "error": "Bad Request",
            "detail": "Una tarea no puede depender de sí misma.",
        }), 400

    depends_on_task = db.session.get(OpeningTaskORM, depends_on_task_id)

    if not depends_on_task or depends_on_task.opening_id != opening_id:
        return jsonify({
            "error": "Bad Request",
            "detail": "La tarea dependencia no pertenece a esta apertura.",
        }), 400

    dependency_type = str(
        data.get("dependency_type") or OpeningDependencyType.BLOCKER
    ).strip().upper()

    if dependency_type not in OpeningDependencyType.ALL:
        return jsonify({
            "error": "Bad Request",
            "detail": "Tipo de dependencia inválido.",
            "allowed": list(OpeningDependencyType.ALL),
        }), 400

    try:
        dependency = OpeningTaskDependencyORM(
            task_id=task_id,
            depends_on_task_id=depends_on_task_id,
            dependency_type=dependency_type,
            created_by=_current_user_id(),
        )

        db.session.add(dependency)
        db.session.flush()

        serialized_dependency = _serialize_task_dependency(dependency)

        _audit_opening(
            opening_id,
            OpeningAuditAction.TASK_DEPENDENCY_CREATED,
            entity_type="TASK_DEPENDENCY",
            entity_id=dependency.id,
            new_value_json=serialized_dependency,
            metadata_json={
                "task_id": task_id,
                "depends_on_task_id": depends_on_task_id,
            },
        )

        db.session.commit()

        return jsonify({
            "message": "Dependencia creada.",
            "item": serialized_dependency,
        }), 201

    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "Conflict",
            "detail": "La dependencia ya existe.",
        }), 409


@openings_bp.route(
    "/<int:opening_id>/task-dependencies/<int:dependency_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_task_dependency(opening_id: int, dependency_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    dependency = db.session.get(OpeningTaskDependencyORM, dependency_id)

    if not dependency:
        return jsonify({
            "error": "Not Found",
            "detail": "Dependencia no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, dependency.task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Dependencia no encontrada para esta apertura.",
        }), 404

    old_value = _serialize_task_dependency(dependency)

    _audit_opening(
        opening_id,
        OpeningAuditAction.TASK_DEPENDENCY_DELETED,
        entity_type="TASK_DEPENDENCY",
        entity_id=dependency.id,
        old_value_json=old_value,
        metadata_json={
            "task_id": dependency.task_id,
            "depends_on_task_id": dependency.depends_on_task_id,
        },
    )

    db.session.delete(dependency)
    db.session.commit()

    return jsonify({
        "message": "Dependencia eliminada.",
    }), 200
    
@openings_bp.route("/<int:opening_id>/task-blockers", methods=["GET"])
@jwt_required()
def list_opening_task_blockers(opening_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    status = (request.args.get("status") or "").strip().upper()
    task_id = request.args.get("task_id", default=None, type=int)

    query = OpeningTaskBlockerORM.query.filter(
        OpeningTaskBlockerORM.opening_id == opening_id,
    )

    if status:
        if status not in OpeningTaskBlockerStatus.ALL:
            return jsonify({
                "error": "Bad Request",
                "detail": "Estatus de bloqueo inválido.",
            }), 400

        query = query.filter(OpeningTaskBlockerORM.status == status)

    if task_id:
        task = db.session.get(OpeningTaskORM, task_id)

        if not task or task.opening_id != opening_id:
            return jsonify({
                "error": "Not Found",
                "detail": "Tarea no encontrada para esta apertura.",
            }), 404

        query = query.filter(OpeningTaskBlockerORM.blocked_task_id == task_id)

    blockers = (
        query
        .order_by(
            OpeningTaskBlockerORM.status.asc(),
            OpeningTaskBlockerORM.created_at.desc(),
            OpeningTaskBlockerORM.id.desc(),
        )
        .all()
    )

    return jsonify({
        "items": [
            _serialize_task_blocker(blocker)
            for blocker in blockers
        ],
    }), 200


@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>/blockers", methods=["POST"])
@jwt_required()
def create_task_blocker(opening_id: int, task_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    data = request.get_json(silent=True) or {}

    blocker_type = str(
        data.get("blocker_type") or OpeningTaskBlockerType.OTHER
    ).strip().upper()

    impact_level = str(
        data.get("impact_level") or OpeningTaskBlockerImpact.MEDIUM
    ).strip().upper()

    reason = str(data.get("reason") or "").strip()
    blocking_task_id = data.get("blocking_task_id")

    if blocker_type not in OpeningTaskBlockerType.ALL:
        return jsonify({
            "error": "Bad Request",
            "detail": "Tipo de bloqueo inválido.",
        }), 400

    if impact_level not in OpeningTaskBlockerImpact.ALL:
        return jsonify({
            "error": "Bad Request",
            "detail": "Nivel de impacto inválido.",
        }), 400

    if not reason:
        return jsonify({
            "error": "Bad Request",
            "detail": "El motivo del bloqueo es obligatorio.",
        }), 400

    parsed_blocking_task_id = None

    if blocker_type == OpeningTaskBlockerType.TASK:
        if not blocking_task_id:
            return jsonify({
                "error": "Bad Request",
                "detail": "El bloqueo por tarea requiere una tarea bloqueante.",
            }), 400

        try:
            parsed_blocking_task_id = int(blocking_task_id)
        except (TypeError, ValueError):
            return jsonify({
                "error": "Bad Request",
                "detail": "La tarea bloqueante es inválida.",
            }), 400

        if parsed_blocking_task_id == task_id:
            return jsonify({
                "error": "Bad Request",
                "detail": "Una tarea no puede bloquearse a sí misma.",
            }), 400

        blocking_task = db.session.get(OpeningTaskORM, parsed_blocking_task_id)

        if not blocking_task or blocking_task.opening_id != opening_id:
            return jsonify({
                "error": "Bad Request",
                "detail": "La tarea bloqueante no pertenece a esta apertura.",
            }), 400

    elif blocking_task_id:
        try:
            parsed_blocking_task_id = int(blocking_task_id)
        except (TypeError, ValueError):
            return jsonify({
                "error": "Bad Request",
                "detail": "La tarea bloqueante es inválida.",
            }), 400

        if parsed_blocking_task_id == task_id:
            return jsonify({
                "error": "Bad Request",
                "detail": "Una tarea no puede bloquearse a sí misma.",
            }), 400

        blocking_task = db.session.get(OpeningTaskORM, parsed_blocking_task_id)

        if not blocking_task or blocking_task.opening_id != opening_id:
            return jsonify({
                "error": "Bad Request",
                "detail": "La tarea bloqueante no pertenece a esta apertura.",
            }), 400

    existing_active = (
        OpeningTaskBlockerORM.query
        .filter(
            OpeningTaskBlockerORM.opening_id == opening_id,
            OpeningTaskBlockerORM.blocked_task_id == task_id,
            OpeningTaskBlockerORM.status == OpeningTaskBlockerStatus.ACTIVE,
            OpeningTaskBlockerORM.blocker_type == blocker_type,
            OpeningTaskBlockerORM.blocking_task_id == parsed_blocking_task_id,
        )
        .first()
    )

    if existing_active:
        return jsonify({
            "error": "Conflict",
            "detail": "Ya existe un bloqueo activo equivalente para esta tarea.",
            "item": _serialize_task_blocker(existing_active),
        }), 409

    blocker = OpeningTaskBlockerORM(
        opening_id=opening_id,
        blocked_task_id=task_id,
        blocker_type=blocker_type,
        blocking_task_id=parsed_blocking_task_id,
        reason=reason,
        impact_level=impact_level,
        status=OpeningTaskBlockerStatus.ACTIVE,
        created_by=_current_user_id(),
    )

    db.session.add(blocker)
    db.session.flush()

    serialized_blocker = _serialize_task_blocker(blocker)

    _audit_opening(
        opening_id,
        OpeningAuditAction.TASK_BLOCKER_CREATED,
        entity_type="TASK_BLOCKER",
        entity_id=blocker.id,
        new_value_json=serialized_blocker,
        metadata_json={
            "blocked_task_id": task_id,
            "blocking_task_id": parsed_blocking_task_id,
            "blocker_type": blocker_type,
            "impact_level": impact_level,
        },
    )

    db.session.commit()

    return jsonify({
        "message": "Bloqueo creado.",
        "item": serialized_blocker,
    }), 201


@openings_bp.route(
    "/<int:opening_id>/task-blockers/<int:blocker_id>/resolve",
    methods=["PATCH"],
)
@jwt_required()
def resolve_task_blocker(opening_id: int, blocker_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    blocker = db.session.get(OpeningTaskBlockerORM, blocker_id)

    if not blocker or blocker.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Bloqueo no encontrado para esta apertura.",
        }), 404

    if blocker.status == OpeningTaskBlockerStatus.RESOLVED:
        return jsonify({
            "error": "Conflict",
            "detail": "El bloqueo ya está resuelto.",
            "item": _serialize_task_blocker(blocker),
        }), 409

    data = request.get_json(silent=True) or {}
    resolution_comment = str(data.get("resolution_comment") or "").strip()

    old_value = _serialize_task_blocker(blocker)

    blocker.status = OpeningTaskBlockerStatus.RESOLVED
    blocker.resolved_by = _current_user_id()
    blocker.resolved_at = _utc_now()
    blocker.resolution_comment = resolution_comment or None

    serialized_blocker = _serialize_task_blocker(blocker)

    _audit_opening(
        opening_id,
        OpeningAuditAction.TASK_BLOCKER_RESOLVED,
        entity_type="TASK_BLOCKER",
        entity_id=blocker.id,
        old_value_json=old_value,
        new_value_json=serialized_blocker,
        metadata_json={
            "blocked_task_id": blocker.blocked_task_id,
            "blocking_task_id": blocker.blocking_task_id,
        },
    )

    db.session.commit()

    return jsonify({
        "message": "Bloqueo resuelto.",
        "item": serialized_blocker,
    }), 200    

@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>/documents", methods=["GET"])
@jwt_required()
def list_task_documents(opening_id: int, task_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    links = (
        OpeningTaskDocumentLinkORM.query
        .filter(
            OpeningTaskDocumentLinkORM.opening_id == opening_id,
            OpeningTaskDocumentLinkORM.task_id == task_id,
            OpeningTaskDocumentLinkORM.status == "ACTIVE",
        )
        .order_by(OpeningTaskDocumentLinkORM.linked_at.desc())
        .all()
    )

    return jsonify({
        "items": [
            _serialize_task_document_link(link)
            for link in links
        ],
    }), 200
    
@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>/documents/upload", methods=["POST"])
@jwt_required()
def upload_task_document(opening_id: int, task_id: int):
    denied = _require_openings_admin()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    if "file" not in request.files:
        return jsonify({
            "error": "Bad Request",
            "detail": "Debes enviar un archivo en el campo 'file'.",
        }), 400

    uploaded_file = request.files["file"]

    if not uploaded_file or not uploaded_file.filename:
        return jsonify({
            "error": "Bad Request",
            "detail": "El archivo enviado no tiene nombre válido.",
        }), 400

    current_user_id = _current_user_id()

    if not current_user_id:
        return jsonify({
            "error": "Unauthorized",
            "detail": "No se pudo resolver el usuario autenticado actual.",
        }), 401

    report_type_key = (
        request.form.get("report_type_key")
        or "internal_documents"
    ).strip()

    document_role = (
        request.form.get("document_role")
        or "EVIDENCE"
    ).strip().upper()

    notes = str(request.form.get("notes") or "").strip() or None
    
    cutoff_date = (
    request.form.get("cutoff_date")
        or _serialize_date(task.planned_due_date)
        or _serialize_date(task.planned_start_date)
        or _serialize_date(opening.target_opening_date)
        or _serialize_date(opening.planned_start_date)
        or _utc_now().date().isoformat()
    )

    try:
        file_bytes = uploaded_file.read()

        upload_result = create_warehouse_document_upload(
            report_type_key=report_type_key,
            original_filename=uploaded_file.filename,
            content_type=uploaded_file.mimetype,
            file_bytes=file_bytes,
            uploaded_by_user_id=current_user_id,
            cutoff_date=cutoff_date,
            audit_details={
                "upload_origin": "openings_task_document",
                "opening_id": opening_id,
                "task_id": task_id,
                "document_role": document_role,
                "cutoff_date_source": "task_or_opening_context",
            },
        )

        warehouse_upload_id = int(upload_result["upload_id"])

        existing_link = (
            OpeningTaskDocumentLinkORM.query
            .filter(
                OpeningTaskDocumentLinkORM.opening_id == opening_id,
                OpeningTaskDocumentLinkORM.task_id == task_id,
                OpeningTaskDocumentLinkORM.warehouse_upload_id == warehouse_upload_id,
                OpeningTaskDocumentLinkORM.status == "ACTIVE",
            )
            .first()
        )

        if existing_link:
            return jsonify({
                "error": "Conflict",
                "detail": "Este documento ya está vinculado activamente a la tarea.",
                "item": _serialize_task_document_link(existing_link),
            }), 409

        link = OpeningTaskDocumentLinkORM(
            opening_id=opening_id,
            task_id=task_id,
            warehouse_upload_id=warehouse_upload_id,
            document_role=document_role,
            notes=notes,
            status="ACTIVE",
            linked_by=current_user_id,
        )

        db.session.add(link)
        db.session.flush()

        serialized_link = _serialize_task_document_link(link)

        _audit_opening(
            opening_id,
            OpeningAuditAction.DOCUMENT_LINKED,
            entity_type="TASK_DOCUMENT_LINK",
            entity_id=link.id,
            new_value_json=serialized_link,
            metadata_json={
                "task_id": task_id,
                "warehouse_upload_id": warehouse_upload_id,
                "document_role": document_role,
                "duplicate_detected": upload_result.get("duplicate_detected"),
                "duplicate_upload_id": upload_result.get("duplicate_upload_id"),
            },
        )

        db.session.commit()

        return jsonify({
            "message": "Documento subido y vinculado correctamente.",
            "item": serialized_link,
            "upload": upload_result,
        }), 201

    except WarehouseDocumentValidationError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Bad Request",
            "detail": str(exc),
        }), 400

    except WarehouseDocumentUploadError as exc:
        db.session.rollback()
        return jsonify({
            "error": "Upload Error",
            "detail": str(exc),
        }), 500

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error inesperado subiendo documento de tarea de apertura."
        )
        return jsonify({
            "error": "Internal Server Error",
            "detail": "Ocurrió un error al subir y vincular el documento.",
        }), 500

@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>/comments", methods=["GET"])
@jwt_required()
def list_task_comments(opening_id: int, task_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    comments = (
        OpeningTaskCommentORM.query
        .filter(
            OpeningTaskCommentORM.opening_id == opening_id,
            OpeningTaskCommentORM.task_id == task_id,
        )
        .order_by(OpeningTaskCommentORM.created_at.asc(), OpeningTaskCommentORM.id.asc())
        .all()
    )

    return jsonify({
        "items": [
            _serialize_task_comment(comment)
            for comment in comments
        ],
    }), 200


@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>/comments", methods=["POST"])
@jwt_required()
def create_task_comment(opening_id: int, task_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    data = request.get_json(silent=True) or {}
    comment_text = str(data.get("comment") or "").strip()

    if not comment_text:
        return jsonify({
            "error": "Bad Request",
            "detail": "El comentario es obligatorio.",
        }), 400

    comment = OpeningTaskCommentORM(
        opening_id=opening_id,
        task_id=task_id,
        comment=comment_text,
        is_system_event=bool(data.get("is_system_event") or False),
        created_by=_current_user_id(),
    )

    db.session.add(comment)
    db.session.flush()

    serialized_comment = _serialize_task_comment(comment)

    _audit_opening(
        opening_id,
        OpeningAuditAction.TASK_COMMENT_CREATED,
        entity_type="TASK_COMMENT",
        entity_id=comment.id,
        new_value_json=serialized_comment,
        metadata_json={
            "task_id": task_id,
        },
    )

    db.session.commit()

    return jsonify({
        "message": "Comentario agregado.",
        "item": serialized_comment,
    }), 201
    
@openings_bp.route("/<int:opening_id>/tasks/<int:task_id>/timeline", methods=["GET"])
@jwt_required()
def get_task_timeline(opening_id: int, task_id: int):
    denied = _require_openings_read()
    if denied:
        return denied

    opening = db.session.get(OpeningORM, opening_id)

    if not opening:
        return jsonify({
            "error": "Not Found",
            "detail": "Apertura no encontrada.",
        }), 404

    task = db.session.get(OpeningTaskORM, task_id)

    if not task or task.opening_id != opening_id:
        return jsonify({
            "error": "Not Found",
            "detail": "Tarea no encontrada para esta apertura.",
        }), 404

    audit_logs = (
        OpeningAuditLogORM.query
        .filter(
            OpeningAuditLogORM.opening_id == opening_id,
            OpeningAuditLogORM.entity_type.in_(
                (
                    "TASK",
                    "TASK_DEPENDENCY",
                    "TASK_BLOCKER",
                )
            ),
        )
        .order_by(
            OpeningAuditLogORM.created_at.desc(),
            OpeningAuditLogORM.id.desc(),
        )
        .all()
    )

    comments = (
        OpeningTaskCommentORM.query
        .filter(
            OpeningTaskCommentORM.opening_id == opening_id,
            OpeningTaskCommentORM.task_id == task_id,
        )
        .order_by(
            OpeningTaskCommentORM.created_at.desc(),
            OpeningTaskCommentORM.id.desc(),
        )
        .all()
    )

    events = [
        _build_task_audit_timeline_event(audit_log)
        for audit_log in audit_logs
        if _audit_log_belongs_to_task(audit_log, task_id)
    ]

    events.extend(
        _build_task_comment_timeline_event(comment)
        for comment in comments
    )

    events.sort(
        key=lambda event: (
            event.get("created_at") or "",
            str(event.get("id") or ""),
        ),
        reverse=True,
    )

    return jsonify({
        "items": events,
    }), 200