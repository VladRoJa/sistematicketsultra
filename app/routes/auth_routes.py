# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\auth_routes.py

# -------------------------------------------------------------------------------
# BLUEPRINT: AUTENTICACIÓN (LOGIN, SESIÓN)
# -------------------------------------------------------------------------------

from flask import Blueprint, request, jsonify
from flask_cors import CORS, cross_origin
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from datetime import timedelta
from app.models.user_model import UserORM
import logging
from config import Config

# Configurar logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

auth_bp = Blueprint('auth', __name__)

# -------------------------------------------------------------------------------
# RUTA: LOGIN (Generar token JWT)
# -------------------------------------------------------------------------------

@auth_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    origin = request.headers.get('Origin')
    print("🌐 Origin recibido:", origin)

    if request.method == 'OPTIONS':
        # RESPUESTA PARA EL PREFLIGHT
        response = make_response('', 204)
        response.headers.add("Access-Control-Allow-Origin", origin)
        response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.add("Access-Control-Allow-Methods", "POST,OPTIONS")
        response.headers.add("Access-Control-Allow-Credentials", "true")
        return response

    try:
        data = request.get_json()
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({"message": "Usuario y contraseña son obligatorios"}), 400

        user = UserORM.get_by_username(username)
        if user and user.verify_password(password):
            access_token = create_access_token(
                identity=str(user.id),
                expires_delta=timedelta(hours=1)
            )
            response = jsonify({
                "message": "Login exitoso",
                "token": access_token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "rol": user.rol,
                    "id_sucursal": user.id_sucursal
                }
            })
            response.headers.add("Access-Control-Allow-Origin", origin)
            response.headers.add("Access-Control-Allow-Credentials", "true")
            return response, 200

        return jsonify({"message": "Credenciales incorrectas"}), 401

    except Exception as e:
        print(f"❌ Error inesperado en login: {e}")
        return jsonify({"message": "Error interno en el servidor"}), 500
# -------------------------------------------------------------------------------
# RUTA: OBTENER INFORMACIÓN DE SESIÓN ACTIVA
# -------------------------------------------------------------------------------

@cross_origin(origins=Config.CORS_ORIGINS, supports_credentials=True)
@auth_bp.route('/session-info', methods=['GET', 'OPTIONS'])
@jwt_required()
def session_info():
    if request.method == 'OPTIONS':
        return '', 204

    try:
        current_user_id = get_jwt_identity()
        logger.info(f"🔐 JWT recibido para ID de usuario: {current_user_id}")

        user = UserORM.get_by_id(current_user_id)
        if not user:
            logger.warning(f"⚠️ Usuario no encontrado para ID: {current_user_id}")
            return jsonify({"message": "Usuario no encontrado"}), 404

        return jsonify({
            "user": {
                "id": user.id,
                "username": user.username,
                "rol": user.rol,
                "id_sucursal": user.id_sucursal
            }
        }), 200

    except Exception as e:
        logger.error(f"❌ Error inesperado en session-info: {e}")
        return jsonify({"message": "Error en sesión"}), 500

