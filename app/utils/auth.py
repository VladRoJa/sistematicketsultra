#C:\Users\Vladimir\Documents\Sistema tickets\app\utils\auth.py

from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from app.models.user_model import User  # Asegúrate de que la ruta sea correcta

def requiere_rol(roles_permitidos):
    def wrapper(func):
        def decorated_function(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            
            user = User.get_user_by_id(user_id)
            if not user or user.rol not in roles_permitidos:
                return jsonify({"error": "No tienes permisos para acceder a esta ruta"}), 403
            
            return func(*args, **kwargs)
        return decorated_function
    return wrapper
