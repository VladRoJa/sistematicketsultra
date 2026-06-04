#   backend\app\routes\openings_routes.py


from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from flask import Blueprint, jsonify, request
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