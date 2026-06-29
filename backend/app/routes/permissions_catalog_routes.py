# backend/app/routes/permissions_catalog_routes.py

import os
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.planning_targets import PlanningOperatorORM
from app.models.permissions import (
    PermissionActionORM,
    PermissionModuleORM,
    PermissionRouteMapORM,
    PermissionGrantORM,
    PermissionGrantAuditLogORM,
)
from app.models.sucursal_model import Sucursal
from app.models.user_model import UserORM
from app.models.warehouse import WarehouseOperatorORM


permissions_catalog_bp = Blueprint("permissions_catalog", __name__)

PERMISSIONS_CATALOG_ADMIN_ROLES = {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}

LEGACY_ADMIN_ROLES = {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}
LEGACY_INVENTORY_GLOBAL_WRITE_ROLES = LEGACY_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SISTEMAS",
    "TECNICO",
}
LEGACY_INVENTORY_SCOPED_WRITE_ROLES = {
    "SR_MANTENIMIENTO",
    "AUX_MANTENIMIENTO",
}
LEGACY_PM_VIEW_ROLES = LEGACY_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
    "AUX_MANTENIMIENTO",
    "SISTEMAS",
    "TECNICO",
    "GERENTE",
    "GERENTE_REGIONAL",
    "LECTOR_GLOBAL",
}
LEGACY_PM_EXECUTE_ROLES = LEGACY_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
    "AUX_MANTENIMIENTO",
    "SISTEMAS",
    "TECNICO",
}
LEGACY_PM_VALIDATE_ROLES = LEGACY_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
}
LEGACY_PM_CONFIGURE_ROLES = LEGACY_ADMIN_ROLES | {
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
}


def _normalize_role(user) -> str:
    return str(getattr(user, "rol", "") or "").strip().upper()


def _is_admin_role(role: str) -> bool:
    return role in LEGACY_ADMIN_ROLES


def _safe_bool(value) -> bool:
    return bool(value)


def _get_user_assigned_sucursal_ids(user) -> list[int]:
    values = []

    raw_values = getattr(user, "sucursales_ids", []) or []
    if isinstance(raw_values, list):
        values.extend(raw_values)

    primary_sucursal_id = getattr(user, "sucursal_id", None)
    if primary_sucursal_id is not None:
        values.append(primary_sucursal_id)

    normalized = []
    for value in values:
        try:
            normalized.append(int(value))
        except (TypeError, ValueError):
            continue

    return sorted(set(normalized))


def _get_user_sucursales_payload(user) -> list[dict]:
    sucursal_ids = _get_user_assigned_sucursal_ids(user)

    if not sucursal_ids:
        return []

    sucursales = (
        Sucursal.query
        .filter(Sucursal.sucursal_id.in_(sucursal_ids))
        .order_by(Sucursal.sucursal.asc())
        .all()
    )

    by_id = {
        int(sucursal.sucursal_id): sucursal
        for sucursal in sucursales
    }

    payload = []
    for sucursal_id in sucursal_ids:
        sucursal = by_id.get(sucursal_id)
        payload.append({
            "sucursal_id": sucursal_id,
            "name": getattr(sucursal, "sucursal", None) if sucursal else None,
            "operational_status": (
                getattr(sucursal, "operational_status", None)
                if sucursal else None
            ),
            "is_primary": sucursal_id == getattr(user, "sucursal_id", None),
        })

    return payload


def _get_target_context(user) -> dict:
    warehouse_operator = WarehouseOperatorORM.query.filter_by(
        user_id=user.id,
    ).first()

    planning_operator = PlanningOperatorORM.query.filter_by(
        user_id=user.id,
        is_active=True,
    ).first()

    return {
        "role": _normalize_role(user),
        "sucursal_ids": _get_user_assigned_sucursal_ids(user),
        "warehouse_operator": warehouse_operator,
        "planning_operator": planning_operator,
        "allow_ticket_delete_all": (
            os.getenv("ALLOW_TICKET_DELETE_ALL", "")
            .strip()
            .lower()
            in {"1", "true", "yes", "si", "sí"}
        ),
    }


def _decision(
    *,
    allowed: bool,
    source: str,
    reason: str,
    scope_type: str = "none",
    scope_values=None,
    details=None,
) -> dict:
    return {
        "allowed": bool(allowed),
        "source": source,
        "reason": reason,
        "scope_type": scope_type,
        "scope_values": scope_values or [],
        "details": details or {},
    }


def _effective_action_decision(action, user, context: dict) -> dict:
    role = context["role"]
    sucursal_ids = context["sucursal_ids"]
    warehouse_operator = context["warehouse_operator"]
    planning_operator = context["planning_operator"]
    full_key = action.full_key

    is_admin = _is_admin_role(role)

    # Usuarios / catálogos
    if full_key == "users.manage":
        return _decision(
            allowed=is_admin,
            source="legacy_role",
            reason="admin_role_required",
            scope_type="global" if is_admin else "none",
        )

    if full_key == "catalogs.manage":
        return _decision(
            allowed=is_admin,
            source="legacy_role",
            reason="catalog_admin_required",
            scope_type="global" if is_admin else "none",
        )

    # Tickets
    if full_key == "tickets.delete_all":
        allowed = bool(is_admin and context["allow_ticket_delete_all"])
        return _decision(
            allowed=allowed,
            source="legacy_role_env_gate",
            reason=(
                "admin_role_and_env_gate_enabled"
                if allowed
                else "requires_admin_role_and_ALLOW_TICKET_DELETE_ALL"
            ),
            scope_type="global" if allowed else "none",
            details={
                "requires_env": "ALLOW_TICKET_DELETE_ALL=true",
                "env_enabled": context["allow_ticket_delete_all"],
            },
        )

    if full_key.startswith("tickets."):
        if is_admin:
            return _decision(
                allowed=True,
                source="legacy_role",
                reason="admin_ticket_scope",
                scope_type="global",
            )

        if role == "LECTOR_GLOBAL":
            return _decision(
                allowed=full_key in {"tickets.notify"},
                source="legacy_ticket_visibility",
                reason="lector_global_limited_ticket_access",
                scope_type="global" if full_key == "tickets.notify" else "none",
            )

        return _decision(
            allowed=True,
            source="legacy_ticket_visibility",
            reason="ticket_scope_depends_on_filtrar_tickets_por_usuario",
            scope_type="branch_scope",
            scope_values=sucursal_ids,
        )

    # Inventario
    if full_key == "inventory.read":
        allowed = bool(role in LEGACY_INVENTORY_GLOBAL_WRITE_ROLES or sucursal_ids)
        return _decision(
            allowed=allowed,
            source="legacy_inventory_scope",
            reason=(
                "global_inventory_role_or_assigned_branch"
                if allowed
                else "no_inventory_scope"
            ),
            scope_type=(
                "global"
                if role in LEGACY_INVENTORY_GLOBAL_WRITE_ROLES
                else "branch_scope"
            ),
            scope_values=[] if role in LEGACY_INVENTORY_GLOBAL_WRITE_ROLES else sucursal_ids,
        )

    if full_key == "inventory.master_write":
        allowed = role in LEGACY_INVENTORY_GLOBAL_WRITE_ROLES
        return _decision(
            allowed=allowed,
            source="legacy_role",
            reason="inventory_global_write_role_required",
            scope_type="global" if allowed else "none",
        )

    if full_key == "inventory.movement_write":
        if role in LEGACY_INVENTORY_GLOBAL_WRITE_ROLES:
            return _decision(
                allowed=True,
                source="legacy_role",
                reason="inventory_global_write_role",
                scope_type="global",
            )

        allowed = bool(role in LEGACY_INVENTORY_SCOPED_WRITE_ROLES and sucursal_ids)
        return _decision(
            allowed=allowed,
            source="legacy_inventory_branch_scope",
            reason=(
                "inventory_scoped_write_role_with_assigned_branches"
                if allowed
                else "requires_scoped_write_role_and_branch"
            ),
            scope_type="branch_scope" if allowed else "none",
            scope_values=sucursal_ids if allowed else [],
        )

    # PM
    if full_key == "pm.read":
        allowed = role in LEGACY_PM_VIEW_ROLES
        return _decision(
            allowed=allowed,
            source="legacy_pm_roles",
            reason="pm_view_role_allowed" if allowed else "pm_view_role_not_allowed",
            scope_type="global" if is_admin or role == "LECTOR_GLOBAL" else "branch_scope",
            scope_values=[] if is_admin or role == "LECTOR_GLOBAL" else sucursal_ids,
        )

    if full_key == "pm.execute":
        allowed = role in LEGACY_PM_EXECUTE_ROLES
        return _decision(
            allowed=allowed,
            source="legacy_pm_roles",
            reason="pm_execute_role_allowed" if allowed else "pm_execute_role_not_allowed",
            scope_type="global" if is_admin else "branch_scope",
            scope_values=[] if is_admin else sucursal_ids,
        )

    if full_key == "pm.validate":
        allowed = role in LEGACY_PM_VALIDATE_ROLES
        return _decision(
            allowed=allowed,
            source="legacy_pm_roles",
            reason="pm_validate_role_allowed" if allowed else "pm_validate_role_not_allowed",
            scope_type="global" if is_admin else "branch_scope",
            scope_values=[] if is_admin else sucursal_ids,
        )

    if full_key == "pm.configure":
        allowed = role in LEGACY_PM_CONFIGURE_ROLES
        return _decision(
            allowed=allowed,
            source="legacy_pm_roles",
            reason="pm_configure_role_allowed" if allowed else "pm_configure_role_not_allowed",
            scope_type="global" if is_admin else "branch_scope",
            scope_values=[] if is_admin else sucursal_ids,
        )

    # Warehouse
    if full_key == "warehouse.view":
        allowed = warehouse_operator is not None and _safe_bool(
            getattr(warehouse_operator, "can_view", False)
        )
        return _decision(
            allowed=allowed,
            source="warehouse_operator",
            reason="warehouse_can_view" if allowed else "missing_warehouse_can_view",
            scope_type="global" if allowed else "none",
        )

    if full_key == "warehouse.upload":
        allowed = warehouse_operator is not None and _safe_bool(
            getattr(warehouse_operator, "can_upload", False)
        )
        return _decision(
            allowed=allowed,
            source="warehouse_operator",
            reason="warehouse_can_upload" if allowed else "missing_warehouse_can_upload",
            scope_type="global" if allowed else "none",
        )

    if full_key == "warehouse.archive":
        allowed = warehouse_operator is not None and _safe_bool(
            getattr(warehouse_operator, "can_archive", False)
        )
        return _decision(
            allowed=allowed,
            source="warehouse_operator",
            reason="warehouse_can_archive" if allowed else "missing_warehouse_can_archive",
            scope_type="global" if allowed else "none",
        )

    if full_key == "warehouse.catalogs":
        allowed = warehouse_operator is not None and (
            _safe_bool(getattr(warehouse_operator, "can_view", False))
            or _safe_bool(getattr(warehouse_operator, "can_upload", False))
        )
        return _decision(
            allowed=allowed,
            source="warehouse_operator",
            reason=(
                "warehouse_can_view_or_upload"
                if allowed
                else "missing_warehouse_catalog_access"
            ),
            scope_type="global" if allowed else "none",
        )

    # Planning
    if full_key == "planning.read":
        allowed = planning_operator is not None and _safe_bool(
            getattr(planning_operator, "can_view", False)
        )
        return _decision(
            allowed=allowed,
            source="planning_operator",
            reason="planning_can_view" if allowed else "missing_planning_can_view",
            scope_type="global" if allowed else "none",
        )

    planning_flag_map = {
        "planning.edit": "can_edit",
        "planning.submit": "can_submit",
        "planning.approve": "can_approve",
        "planning.publish": "can_publish",
        "planning.configure_model": "can_configure_model",
    }

    if full_key in planning_flag_map:
        flag = planning_flag_map[full_key]
        allowed = planning_operator is not None and _safe_bool(
            getattr(planning_operator, flag, False)
        )
        return _decision(
            allowed=allowed,
            source="planning_operator",
            reason=f"planning_{flag}" if allowed else f"missing_planning_{flag}",
            scope_type="global" if allowed else "none",
        )

    # Track
    if full_key == "track.read":
        allowed = is_admin or role == "LECTOR_GLOBAL"
        return _decision(
            allowed=allowed,
            source="legacy_role",
            reason="track_read_admin_or_lector_global",
            scope_type="global" if allowed else "none",
        )

    if full_key in {"track.run_daily_pipeline", "track.run_agregadoras"}:
        return _decision(
            allowed=is_admin,
            source="legacy_role",
            reason="track_admin_required",
            scope_type="global" if is_admin else "none",
        )

    # Nube corporativa
    if full_key == "internal_documents.view":
        return _decision(
            allowed=True,
            source="authenticated_user",
            reason="internal_documents_visibility_still_evaluated_per_document",
            scope_type="document_visibility",
        )

    if full_key == "internal_documents.manage":
        return _decision(
            allowed=is_admin,
            source="legacy_internal_documents_manager",
            reason=(
                "admin_role_treated_as_manager_in_observability_v1"
                if is_admin
                else "requires_internal_document_manager"
            ),
            scope_type="global" if is_admin else "none",
            details={
                "note": "Observability v1. Manager helper remains real authority."
            },
        )

    # Aperturas
    if full_key == "openings.read":
        return _decision(
            allowed=is_admin,
            source="legacy_openings_access",
            reason="openings_read_observability_v1_admin_only",
            scope_type="global" if is_admin else "none",
        )

    if full_key == "openings.manage":
        return _decision(
            allowed=is_admin,
            source="legacy_role",
            reason="openings_admin_required",
            scope_type="global" if is_admin else "none",
        )

    if full_key == "openings.comment":
        return _decision(
            allowed=is_admin,
            source="legacy_openings_access",
            reason="comment_uses_openings_read_in_current_guard_review",
            scope_type="global" if is_admin else "none",
        )

    # Reportes
    if full_key == "reports.read":
        return _decision(
            allowed=is_admin,
            source="legacy_role",
            reason="reports_read_admin_only_observability_v1",
            scope_type="global" if is_admin else "none",
        )

    if full_key == "reports.create_error_report":
        return _decision(
            allowed=True,
            source="authenticated_user",
            reason="authenticated_users_can_report_errors",
            scope_type="self",
        )

    return _decision(
        allowed=False,
        source="unmapped_observability_v1",
        reason="no_effective_rule_defined_for_action",
    )


def _serialize_effective_action(action, user, context: dict) -> dict:
    decision = _effective_action_decision(action, user, context)

    return {
        "action_id": action.id,
        "module_key": action.module.key if action.module else None,
        "key": action.key,
        "full_key": action.full_key,
        "name": action.name,
        "risk_level": action.risk_level,
        "is_active": action.is_active,
        **decision,
    }


def _current_admin_user_or_error():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None, (
            jsonify({
                "error": "Forbidden",
                "detail": "No autorizado para consultar catálogo de permisos.",
            }),
            403,
        )

    user = UserORM.get_by_id(user_id)
    rol = str(getattr(user, "rol", "") or "").strip().upper() if user else ""

    if rol not in PERMISSIONS_CATALOG_ADMIN_ROLES:
        return None, (
            jsonify({
                "error": "Forbidden",
                "detail": "No autorizado para consultar catálogo de permisos.",
            }),
            403,
        )

    return user, None


def _parse_active_filter():
    value = str(request.args.get("active", "true") or "").strip().lower()

    if value in {"all", "*"}:
        return None

    if value in {"true", "1", "yes", "si", "sí"}:
        return True

    if value in {"false", "0", "no"}:
        return False

    return True


@permissions_catalog_bp.route("/modules", methods=["GET"])
@jwt_required()
def list_permission_modules():
    _, error = _current_admin_user_or_error()
    if error:
        return error

    active_filter = _parse_active_filter()

    query = PermissionModuleORM.query

    if active_filter is not None:
        query = query.filter(PermissionModuleORM.is_active.is_(active_filter))

    modules = query.order_by(PermissionModuleORM.key.asc()).all()

    return jsonify({
        "modules": [
            {
                "id": module.id,
                "key": module.key,
                "name": module.name,
                "description": module.description,
                "is_active": module.is_active,
                "actions_count": len(module.actions or []),
            }
            for module in modules
        ]
    }), 200


@permissions_catalog_bp.route("/actions", methods=["GET"])
@jwt_required()
def list_permission_actions():
    _, error = _current_admin_user_or_error()
    if error:
        return error

    active_filter = _parse_active_filter()
    module_key = str(request.args.get("module", "") or "").strip()
    risk_level = str(request.args.get("risk_level", "") or "").strip().lower()

    query = PermissionActionORM.query.join(PermissionModuleORM)

    if active_filter is not None:
        query = query.filter(PermissionActionORM.is_active.is_(active_filter))

    if module_key:
        query = query.filter(PermissionModuleORM.key == module_key)

    if risk_level:
        query = query.filter(PermissionActionORM.risk_level == risk_level)

    actions = query.order_by(
        PermissionModuleORM.key.asc(),
        PermissionActionORM.key.asc(),
    ).all()

    return jsonify({
        "actions": [
            {
                "id": action.id,
                "module_id": action.module_id,
                "module_key": action.module.key if action.module else None,
                "key": action.key,
                "full_key": action.full_key,
                "name": action.name,
                "description": action.description,
                "risk_level": action.risk_level,
                "is_active": action.is_active,
            }
            for action in actions
        ]
    }), 200


@permissions_catalog_bp.route("/routes", methods=["GET"])
@jwt_required()
def list_permission_route_map():
    _, error = _current_admin_user_or_error()
    if error:
        return error

    active_filter = _parse_active_filter()
    module_key = str(request.args.get("module", "") or "").strip()
    review_status = str(request.args.get("review_status", "") or "").strip()

    query = PermissionRouteMapORM.query.outerjoin(PermissionModuleORM)

    if active_filter is not None:
        query = query.filter(PermissionRouteMapORM.is_active.is_(active_filter))

    if module_key:
        query = query.filter(PermissionModuleORM.key == module_key)

    if review_status:
        query = query.filter(PermissionRouteMapORM.review_status == review_status)

    route_maps = query.order_by(
        PermissionRouteMapORM.source_file.asc(),
        PermissionRouteMapORM.endpoint_function.asc(),
        PermissionRouteMapORM.method.asc(),
    ).all()

    return jsonify({
        "routes": [
            {
                "id": route_map.id,
                "method": route_map.method,
                "route": route_map.route,
                "endpoint_function": route_map.endpoint_function,
                "source_file": route_map.source_file,
                "module_id": route_map.module_id,
                "module_key": route_map.module.key if route_map.module else None,
                "action_id": route_map.action_id,
                "action_full_key": route_map.action.full_key if route_map.action else None,
                "current_guard": route_map.current_guard,
                "current_scope": route_map.current_scope,
                "review_status": route_map.review_status,
                "notes": route_map.notes,
                "is_active": route_map.is_active,
            }
            for route_map in route_maps
        ]
    }), 200

@permissions_catalog_bp.route("/users/<int:user_id>/effective", methods=["GET"])
@jwt_required()
def get_user_effective_permissions(user_id: int):
    _, error = _current_admin_user_or_error()
    if error:
        return error

    target_user = UserORM.get_by_id(user_id)
    if not target_user:
        return jsonify({
            "error": "Not found",
            "detail": "Usuario no encontrado.",
        }), 404

    active_filter = _parse_active_filter()

    query = PermissionActionORM.query.join(PermissionModuleORM)

    if active_filter is not None:
        query = query.filter(PermissionActionORM.is_active.is_(active_filter))

    actions = query.order_by(
        PermissionModuleORM.key.asc(),
        PermissionActionORM.key.asc(),
    ).all()

    context = _get_target_context(target_user)

    effective_actions = [
        _serialize_effective_action(action, target_user, context)
        for action in actions
    ]

    allowed_count = sum(1 for item in effective_actions if item["allowed"])
    denied_count = len(effective_actions) - allowed_count

    warehouse_operator = context["warehouse_operator"]
    planning_operator = context["planning_operator"]

    return jsonify({
        "status": "ok",
        "mode": "observability_v1",
        "authorization_source": "legacy_rules_readonly",
        "note": (
            "Este endpoint es diagnóstico. No reemplaza guards actuales "
            "ni activa permission_grants."
        ),
        "user": {
            "id": target_user.id,
            "username": target_user.username,
            "email": target_user.email,
            "role": context["role"],
            "department_id": target_user.department_id,
            "primary_sucursal_id": target_user.sucursal_id,
            "sucursales": _get_user_sucursales_payload(target_user),
        },
        "summary": {
            "actions_total": len(effective_actions),
            "allowed_count": allowed_count,
            "denied_count": denied_count,
        },
        "operator_context": {
            "warehouse": {
                "exists": warehouse_operator is not None,
                "can_view": bool(getattr(warehouse_operator, "can_view", False))
                if warehouse_operator else False,
                "can_upload": bool(getattr(warehouse_operator, "can_upload", False))
                if warehouse_operator else False,
                "can_archive": bool(getattr(warehouse_operator, "can_archive", False))
                if warehouse_operator else False,
            },
            "planning": {
                "exists": planning_operator is not None,
                "is_active": bool(getattr(planning_operator, "is_active", False))
                if planning_operator else False,
                "can_view": bool(getattr(planning_operator, "can_view", False))
                if planning_operator else False,
                "can_edit": bool(getattr(planning_operator, "can_edit", False))
                if planning_operator else False,
                "can_submit": bool(getattr(planning_operator, "can_submit", False))
                if planning_operator else False,
                "can_approve": bool(getattr(planning_operator, "can_approve", False))
                if planning_operator else False,
                "can_publish": bool(getattr(planning_operator, "can_publish", False))
                if planning_operator else False,
                "can_configure_model": bool(
                    getattr(planning_operator, "can_configure_model", False)
                ) if planning_operator else False,
            },
        },
        "actions": effective_actions,
    }), 200

@permissions_catalog_bp.route("/users/search", methods=["GET"])
@jwt_required()
def search_permission_users():
    _, error = _current_admin_user_or_error()
    if error:
        return error

    q = str(request.args.get("q", "") or "").strip()
    raw_limit = request.args.get("limit", 25)

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 25

    limit = max(1, min(limit, 100))

    query = UserORM.query

    if q:
        q_like = f"%{q.lower()}%"
        filters = [
            db.func.lower(UserORM.username).like(q_like),
            db.func.lower(UserORM.rol).like(q_like),
        ]

        if hasattr(UserORM, "email"):
            filters.append(db.func.lower(UserORM.email).like(q_like))

        try:
            q_id = int(q)
        except (TypeError, ValueError):
            q_id = None

        if q_id is not None:
            filters.append(UserORM.id == q_id)

        query = query.filter(db.or_(*filters))

    users = (
        query
        .order_by(UserORM.username.asc())
        .limit(limit)
        .all()
    )

    return jsonify({
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": getattr(user, "email", None),
                "rol": user.rol,
                "department_id": user.department_id,
                "sucursal_id": user.sucursal_id,
                "sucursales_ids": user.sucursales_ids,
            }
            for user in users
        ]
    }), 200




def _to_iso(value):
    return value.isoformat() if value else None


def _serialize_user_payload(user) -> dict | None:
    if not user:
        return None

    return {
        "id": user.id,
        "username": user.username,
        "email": getattr(user, "email", None),
        "rol": user.rol,
    }


def _serialize_permission_grant(grant) -> dict:
    return {
        "id": grant.id,
        "principal_type": grant.principal_type,
        "principal_user_id": grant.principal_user_id,
        "principal_user": _serialize_user_payload(grant.principal_user),
        "principal_role_key": grant.principal_role_key,
        "module_id": grant.module_id,
        "module_key": grant.module.key if grant.module else None,
        "module_name": grant.module.name if grant.module else None,
        "action_id": grant.action_id,
        "action_full_key": grant.action.full_key if grant.action else None,
        "action_name": grant.action.name if grant.action else None,
        "action_risk_level": grant.action.risk_level if grant.action else None,
        "effect": grant.effect,
        "scope_type": grant.scope_type,
        "scope_branch_id": grant.scope_branch_id,
        "scope_branch_ids": grant.scope_branch_ids or [],
        "scope_department_id": grant.scope_department_id,
        "scope_payload": grant.scope_payload or {},
        "reason": grant.reason,
        "is_active": grant.is_active,
        "starts_at": _to_iso(grant.starts_at),
        "expires_at": _to_iso(grant.expires_at),
        "created_by_user_id": grant.created_by_user_id,
        "created_by_user": _serialize_user_payload(grant.created_by_user),
        "updated_by_user_id": grant.updated_by_user_id,
        "updated_by_user": _serialize_user_payload(grant.updated_by_user),
        "created_at": _to_iso(grant.created_at),
        "updated_at": _to_iso(grant.updated_at),
        "deleted_at": _to_iso(grant.deleted_at),
    }


def _serialize_permission_grant_audit_log(entry) -> dict:
    return {
        "id": entry.id,
        "grant_id": entry.grant_id,
        "event_type": entry.event_type,
        "before_payload": entry.before_payload or {},
        "after_payload": entry.after_payload or {},
        "changed_by_user_id": entry.changed_by_user_id,
        "changed_by_user": _serialize_user_payload(entry.changed_by_user),
        "reason": entry.reason,
        "request_ip": entry.request_ip,
        "user_agent": entry.user_agent,
        "created_at": _to_iso(entry.created_at),
    }


def _parse_optional_int_arg(arg_name: str):
    value = request.args.get(arg_name)

    if value is None or str(value).strip() == "":
        return None, None

    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, (
            jsonify({
                "error": "Bad request",
                "detail": f"El filtro {arg_name} debe ser numérico.",
            }),
            400,
        )


def _parse_limit_offset(default_limit: int = 50, max_limit: int = 200):
    raw_limit = request.args.get("limit", default_limit)
    raw_offset = request.args.get("offset", 0)

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = default_limit

    try:
        offset = int(raw_offset)
    except (TypeError, ValueError):
        offset = 0

    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)

    return limit, offset


def _apply_permission_grant_filters(query):
    active_filter = _parse_active_filter()
    principal_type = str(request.args.get("principal_type", "") or "").strip().lower()
    principal_role_key = str(request.args.get("principal_role_key", "") or "").strip().upper()
    module_key = str(request.args.get("module_key", "") or "").strip()
    action_full_key = str(request.args.get("action_full_key", "") or "").strip()
    effect = str(request.args.get("effect", "") or "").strip().lower()
    scope_type = str(request.args.get("scope_type", "") or "").strip().lower()

    principal_user_id, error = _parse_optional_int_arg("principal_user_id")
    if error:
        return None, error

    module_id, error = _parse_optional_int_arg("module_id")
    if error:
        return None, error

    action_id, error = _parse_optional_int_arg("action_id")
    if error:
        return None, error

    if active_filter is not None:
        query = query.filter(PermissionGrantORM.is_active.is_(active_filter))

    if principal_type:
        query = query.filter(PermissionGrantORM.principal_type == principal_type)

    if principal_user_id is not None:
        query = query.filter(PermissionGrantORM.principal_user_id == principal_user_id)

    if principal_role_key:
        query = query.filter(PermissionGrantORM.principal_role_key == principal_role_key)

    if module_id is not None:
        query = query.filter(PermissionGrantORM.module_id == module_id)

    if module_key:
        query = query.filter(PermissionModuleORM.key == module_key)

    if action_id is not None:
        query = query.filter(PermissionGrantORM.action_id == action_id)

    if action_full_key:
        query = query.filter(PermissionActionORM.full_key == action_full_key)

    if effect:
        query = query.filter(PermissionGrantORM.effect == effect)

    if scope_type:
        query = query.filter(PermissionGrantORM.scope_type == scope_type)

    return query, None


@permissions_catalog_bp.route("/grants", methods=["GET"])
@jwt_required()
def list_permission_grants():
    _, error = _current_admin_user_or_error()
    if error:
        return error

    query = (
        PermissionGrantORM.query
        .outerjoin(PermissionModuleORM, PermissionGrantORM.module_id == PermissionModuleORM.id)
        .outerjoin(PermissionActionORM, PermissionGrantORM.action_id == PermissionActionORM.id)
    )

    query, error = _apply_permission_grant_filters(query)
    if error:
        return error

    total = query.count()
    limit, offset = _parse_limit_offset()

    grants = (
        query
        .order_by(
            PermissionGrantORM.created_at.desc(),
            PermissionGrantORM.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jsonify({
        "status": "ok",
        "mode": "permission_grants_readonly_v1",
        "note": "Endpoint diagnóstico. No crea, edita, borra ni aplica grants.",
        "summary": {
            "total": total,
            "limit": limit,
            "offset": offset,
        },
        "grants": [
            _serialize_permission_grant(grant)
            for grant in grants
        ],
    }), 200


@permissions_catalog_bp.route("/grants/<int:grant_id>", methods=["GET"])
@jwt_required()
def get_permission_grant(grant_id: int):
    _, error = _current_admin_user_or_error()
    if error:
        return error

    grant = PermissionGrantORM.query.get(grant_id)

    if not grant:
        return jsonify({
            "error": "Not found",
            "detail": "Grant no encontrado.",
        }), 404

    return jsonify({
        "status": "ok",
        "mode": "permission_grants_readonly_v1",
        "grant": _serialize_permission_grant(grant),
    }), 200


@permissions_catalog_bp.route("/grants/<int:grant_id>/audit", methods=["GET"])
@jwt_required()
def list_permission_grant_audit_logs(grant_id: int):
    _, error = _current_admin_user_or_error()
    if error:
        return error

    grant = PermissionGrantORM.query.get(grant_id)

    if not grant:
        return jsonify({
            "error": "Not found",
            "detail": "Grant no encontrado.",
        }), 404

    event_type = str(request.args.get("event_type", "") or "").strip().lower()
    limit, offset = _parse_limit_offset(default_limit=50, max_limit=200)

    query = PermissionGrantAuditLogORM.query.filter(
        PermissionGrantAuditLogORM.grant_id == grant_id,
    )

    if event_type:
        query = query.filter(PermissionGrantAuditLogORM.event_type == event_type)

    total = query.count()

    audit_logs = (
        query
        .order_by(
            PermissionGrantAuditLogORM.created_at.desc(),
            PermissionGrantAuditLogORM.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jsonify({
        "status": "ok",
        "mode": "permission_grants_audit_readonly_v1",
        "grant": _serialize_permission_grant(grant),
        "summary": {
            "total": total,
            "limit": limit,
            "offset": offset,
        },
        "audit_logs": [
            _serialize_permission_grant_audit_log(entry)
            for entry in audit_logs
        ],
    }), 200
