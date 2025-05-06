#C:\Users\Vladimir\Documents\Sistema tickets\app\routes\auth_routes.py


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


# Configurar logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

auth_bp = Blueprint('auth', __name__)

# -------------------------------------------------------------------------------
# RUTA: LOGIN (Generar token JWT)
# -------------------------------------------------------------------------------

@auth_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    origin = request.headers.get('Origin') or '*'
    logger.info(f"🛡 Origin recibido en login: {origin}")

    if request.method == 'OPTIONS':
        response = make_response('', 204)
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    try:
        data = request.get_json(force=True) or {}
        logger.info(f"📩 Payload recibido: {data}")

        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        logger.info(f"🧪 Intentando login con username: '{username}' y password: '{password}'")

        if not username or not password:
            logger.warning("⚠️ Faltan username o password en el payload")
            return jsonify({"message": "Usuario y contraseña son obligatorios"}), 400

        user = UserORM.get_by_username(username)
        logger.info(f"🔎 Resultado búsqueda usuario: {user}")

        if user:
            if user.verify_password(password):
                logger.info("✅ Contraseña verificada correctamente")

                token = create_access_token(
                    identity=str(user.id),
                    expires_delta=timedelta(hours=1)
                )
                logger.info(f"🪙 Token generado: {token[:30]}...")

                response_body = {
                    "message": "Login exitoso",
                    "token": token,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "rol": user.rol,
                        "sucursal_id": user.sucursal_id
                    }
                }

                response = jsonify(response_body)
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                logger.info("📤 Login exitoso enviado al frontend")
                return response, 200

            else:
                logger.warning("❌ Contraseña incorrecta")
        else:
            logger.warning("❌ Usuario no encontrado")

        return jsonify({"message": "Credenciales incorrectas"}), 401

    except Exception as e:
        logger.error(f"❌ Error inesperado en login: {e}", exc_info=True)
        return jsonify({"message": "Error interno en el servidor"}), 500

# -------------------------------------------------------------------------------
# RUTA: OBTENER INFORMACIÓN DE SESIÓN ACTIVA
# -------------------------------------------------------------------------------

@auth_bp.route('/session-info', methods=['GET', 'OPTIONS'])
@jwt_required()
def session_info():
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
        logger.error(f"❌ Error inesperado en session-info: {e}")
        return jsonify({"message": "Error en sesión"}), 500
