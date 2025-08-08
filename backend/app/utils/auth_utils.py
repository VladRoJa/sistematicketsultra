# app\utils\auth_utils.py

from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from functools import wraps
from backend.app.models.user_model import UserORM

# -------------------------------------------------------------------------------
# DECORADOR: Requiere estar autenticado (token válido)
# -------------------------------------------------------------------------------
def requiere_auth(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        verify_jwt_in_request()
        return func(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------------------
# DECORADOR: Requiere rol específico (admin, supervisor, etc)
# -------------------------------------------------------------------------------
def requiere_rol(roles_permitidos):
    def decorator(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = UserORM.get_by_id(user_id)

            if not user:
                return jsonify({"mensaje": "Usuario no encontrado"}), 404

            if user.rol not in roles_permitidos:
                return jsonify({"mensaje": "Acceso denegado: Rol insuficiente"}), 403

            return func(*args, **kwargs)
        return decorated_function
    return decorator

# -------------------------------------------------------------------------------
# EJEMPLOS DE DECORADORES DIRECTOS
# -------------------------------------------------------------------------------

def requiere_admin(func):
    """Requiere que el usuario sea ADMINISTRADOR."""
    return requiere_rol(['ADMINISTRADOR'])(func)

def requiere_supervisor(func):
    """Requiere que el usuario sea SUPERVISOR."""
    return requiere_rol(['SUPERVISOR'])(func)

def requiere_admin_o_supervisor(func):
    """Permite acceso si es ADMINISTRADOR o SUPERVISOR."""
    return requiere_rol(['ADMINISTRADOR', 'SUPERVISOR'])(func)

