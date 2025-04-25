# C:\Users\Vladimir\Documents\Sistema tickets\app\utils\auth.py

# ------------------------------------------------------------------------------
# UTILS: Decorador para control de permisos por rol
# ------------------------------------------------------------------------------

from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from app.models.user_model import UserORM

def requiere_rol(roles_permitidos):
    def wrapper(func):
        def decorated_function(*args, **kwargs):
            try:
                verify_jwt_in_request()
                user_id = get_jwt_identity()
                user = UserORM.get_by_id(user_id)

                if not user or user.rol not in roles_permitidos:
                    return jsonify({"error": "No tienes permisos para acceder a esta ruta"}), 403

                return func(*args, **kwargs)

            except Exception as e:
                print(f"❌ Error en requiere_rol: {e}")
                return jsonify({"error": "Error interno en validación de rol"}), 500

        decorated_function.__name__ = func.__name__  # 🛠️ Importante para no romper Flask internamente
        return decorated_function
    return wrapper
