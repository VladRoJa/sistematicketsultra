#app/routes/auth_routes.py

from flask import Blueprint, request, jsonify, session
from flask_cors import CORS
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from app.models.user_model import User
from datetime import timedelta

auth_bp = Blueprint('auth', __name__)
CORS(auth_bp, resources={r"/*": {"origins": "http://localhost:4200"}}, supports_credentials=True)

@auth_bp.route('/session-info', methods=['GET'])
@jwt_required()
def session_info():
    try:
        current_user = get_jwt_identity()
        print(f"📌 Usuario autenticado en session-info: {current_user}")

        user = User.get_user_by_username(current_user)
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        return jsonify({
            "user": {
                "id": user.id,
                "username": user.username,
                "rol": user.rol,
                "id_sucursal": user.id_sucursal
            }
        }), 200
    except Exception as e:
        print(f"❌ Error en session-info: {e}")
        return jsonify({"mensaje": f"Error en session-info: {str(e)}"}), 500


@auth_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    try:
        if request.method == 'OPTIONS':
            return '', 204

        data = request.get_json()
        print("🔍 Datos recibidos:", data)  # <-- Verificar que los datos llegan correctamente

        username = data.get('username')  # Asegúrate de que el nombre de la clave coincide
        password = data.get('password')

        print(f"📌 Recibido: usuario={username}, contraseña={password}")  # <-- Depuración

        user = User.get_user_by_credentials(username, password)

        print(f"🔍 Resultado de la consulta en MySQL: {user}")  # <-- Verificar si MySQL devuelve algo

        if user:
            access_token = create_access_token(identity=user.username, expires_delta=timedelta(hours=1))

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
            return response, 200

        return jsonify({"message": "Credenciales incorrectas"}), 401

    except Exception as e:
        print("❌ Error en login:", e)
        return jsonify({"message": "Error interno en el servidor"}), 500
