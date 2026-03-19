# app/utils/warehouse_access.py

from flask_jwt_extended import get_jwt_identity
from app.models import WarehouseOperatorORM
from flask import jsonify




def is_current_user_warehouse_operator() -> bool:
    """
    Valida si el usuario autenticado actual pertenece a la allowlist
    base de operadores de Warehouse.

    F1.1:
    - No usa roles globales
    - No usa permisos por acción
    - Solo valida pertenencia a warehouse_operators por user_id
    """
    current_user_id = get_jwt_identity()

    if current_user_id is None:
        return False

    try:
        current_user_id = int(current_user_id)
    except (TypeError, ValueError):
        return False

    operator = WarehouseOperatorORM.query.filter_by(user_id=current_user_id).first()
    return operator is not None

def require_warehouse_operator():
    """
    Valida acceso base al módulo Warehouse para el usuario autenticado actual.

    Debe usarse dentro de rutas protegidas con @jwt_required().
    Si el usuario no pertenece a la allowlist de Warehouse, devuelve
    una respuesta HTTP 403 reutilizable.
    """
    if not is_current_user_warehouse_operator():
        return jsonify({
            "error": "Forbidden",
            "detail": "No autorizado para acceder a Warehouse"
        }), 403

    return None
