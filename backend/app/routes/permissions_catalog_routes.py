# backend/app/routes/permissions_catalog_routes.py

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.permissions import (
    PermissionActionORM,
    PermissionModuleORM,
    PermissionRouteMapORM,
)
from app.models.user_model import UserORM


permissions_catalog_bp = Blueprint("permissions_catalog", __name__)

PERMISSIONS_CATALOG_ADMIN_ROLES = {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}


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
