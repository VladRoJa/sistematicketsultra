# app/utils/warehouse_access.py

from flask import jsonify
from flask_jwt_extended import get_jwt_identity

from app.models import WarehouseOperatorORM


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


def require_warehouse_archive():
    operator = get_current_warehouse_operator()

    if operator is None or not bool(operator.can_archive):
        return _forbidden_response("No autorizado para archivar documentos de Warehouse")

    return None
