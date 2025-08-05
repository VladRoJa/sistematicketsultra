#app\routes\auth_routes.py


# -------------------------------------------------------------------------------
# BLUEPRINT: AUTENTICACIÓN (LOGIN, SESIÓN)
# -------------------------------------------------------------------------------

from flask import Blueprint, request, jsonify, make_response, Response
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from datetime import timedelta
from app.models.user_model import UserORM
import logging
from config import Config
import json
from app.utils.error_handler import manejar_error


# Configurar logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

auth_bp = Blueprint('auth', __name__)

# -------------------------------------------------------------------------------
# RUTA: LOGIN (Generar token JWT)
# -------------------------------------------------------------------------------

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json(force=True)
        print("📩 Payload recibido:", data)

        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        print(f"🧪 Login con usuario: {username}")

        user = UserORM.get_by_username(username)
        if user:
            print("🔎 Usuario encontrado:", user)
            if user.verify_password(password):
                print("✅ Contraseña correcta")

                # ✅ Usar configuración global de expiración
                token = create_access_token(identity=str(user.id))
                print("🪙 Token:", token[:20])

                return jsonify({
                    "message": "Login exitoso",
                    "token": token,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "rol": user.rol,
                        "sucursal_id": user.sucursal_id
                    }
                }), 200
            else:
                print("❌ Contraseña incorrecta")
        else:
            print("❌ Usuario no encontrado")

        return jsonify({"message": "Credenciales incorrectas"}), 401

    except Exception as e:
        return manejar_error(e, "login")


# -------------------------------------------------------------------------------
# RUTA: OBTENER INFORMACIÓN DE SESIÓN ACTIVA
# -------------------------------------------------------------------------------

@auth_bp.route('/session-info', methods=['GET', 'OPTIONS'])
@jwt_required()
def session_info():
    from flask_jwt_extended import get_jwt
    import datetime

    # 📅 Depuración: ver cuándo expira el token
    jwt_data = get_jwt()
    exp_timestamp = jwt_data.get("exp")
    exp_datetime = datetime.datetime.fromtimestamp(exp_timestamp)
    logger.info(f"🕒 Token expira en: {exp_datetime} (timestamp: {exp_timestamp})")

    origin = request.headers.get('Origin') or '*'
    logger.info(f"🛡 Origin recibido en session-info: {origin}")

    if request.method == 'OPTIONS':
        response = make_response('', 204)
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    try:
        current_user_id = get_jwt_identity()
        logger.info(f"🔐 JWT recibido para ID de usuario: {current_user_id}")

        user = UserORM.get_by_id(current_user_id)
        if not user:
            logger.warning(f"⚠️ Usuario no encontrado para ID: {current_user_id}")
            return jsonify({"message": "Usuario no encontrado"}), 404

        response = jsonify({
            "user": {
                "id": user.id,
                "username": user.username,
                "rol": user.rol,
                "sucursal_id": user.sucursal_id
            }
        })
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 200

    except Exception as e:
        return manejar_error(e, "session-info")
