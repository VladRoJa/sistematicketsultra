# app/utils/warehouse_access.py

from flask import jsonify, current_app, has_app_context
from flask_jwt_extended import get_jwt_identity

from app.models import WarehouseOperatorORM, UserORM


def get_current_warehouse_operator() -> WarehouseOperatorORM | None:
    """
    Devuelve el operador Warehouse del usuario autenticado actual.

    Fuente real:
    - warehouse_operators por user_id.
    """
    current_user_id = get_jwt_identity()

    if current_user_id is None:
        return None

    try:
        current_user_id = int(current_user_id)
    except (TypeError, ValueError):
        return None

    return WarehouseOperatorORM.query.filter_by(user_id=current_user_id).first()


def is_current_user_warehouse_operator() -> bool:
    """
    Valida si el usuario autenticado actual pertenece a la allowlist
    base de operadores de Warehouse.
    """
    return get_current_warehouse_operator() is not None


def _forbidden_response(detail: str):
    return jsonify({
        "error": "Forbidden",
        "detail": detail,
    }), 403


def require_warehouse_operator():
    """
    Valida acceso base al módulo Warehouse.

    Mantiene compatibilidad con rutas que solo necesitan saber si el usuario
    pertenece a la allowlist.
    """
    if not is_current_user_warehouse_operator():
        return _forbidden_response("No autorizado para acceder a Warehouse")

    return None


def require_warehouse_view():
    operator = get_current_warehouse_operator()

    if operator is None or not bool(operator.can_view):
        return _forbidden_response("No autorizado para consultar Warehouse")

    return None


def require_warehouse_catalogs():
    operator = get_current_warehouse_operator()

    if operator is None or not (
        bool(operator.can_view) or bool(operator.can_upload)
    ):
        return _forbidden_response("No autorizado para consultar catálogos de Warehouse")

    return None


def require_warehouse_upload():
    operator = get_current_warehouse_operator()

    if operator is None or not bool(operator.can_upload):
        return _forbidden_response("No autorizado para subir documentos a Warehouse")

    return None


def warehouse_archive_grants_enabled():
    """Veto opcional de archivar, además de la allowlist can_archive."""
    return has_app_context() and current_app.config.get(
        "PERMISSIONS_WAREHOUSE_ARCHIVE_GRANTS_ENABLED", False
    ) is True


def require_warehouse_archive():
    operator = get_current_warehouse_operator()

    if operator is None or not bool(operator.can_archive):
        return _forbidden_response("No autorizado para archivar documentos de Warehouse")

    # La casilla es solo un veto; un ALLOW nunca crea operador ni can_archive.
    # Con el flag OFF se conserva el guard legacy sin consultar grants.
    if warehouse_archive_grants_enabled():
        user = UserORM.get_by_id(int(get_jwt_identity()))
        if user is None:
            return _forbidden_response("No autorizado para archivar documentos de Warehouse")
        from app.routes.permissions_catalog_routes import _simple_global_action_grant_override
        decision = _simple_global_action_grant_override(
            user=user, action_full_key="warehouse.archive"
        )
        if decision is False:
            return _forbidden_response("No tienes habilitado archivar documentos de Warehouse")

    return None
