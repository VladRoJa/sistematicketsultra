#app/routes/auth_routes.py

from flask import Blueprint, request, jsonify, session
from flask_cors import CORS
from flask_jwt_extended import create_access_token
from app.models.user_model import User
from datetime import timedelta

auth_bp = Blueprint('auth', __name__)
CORS(auth_bp, resources={r"/*": {"origins": "http://localhost:4200"}}, supports_credentials=True)

@auth_bp.route('/session-info', methods=['GET'])
def session_info():
    return jsonify(dict(session)), 200


@auth_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    try:
        # Manejar preflight request (prevenir errores CORS)
        if request.method == 'OPTIONS':
            return '', 204

        data = request.get_json()
        username = data.get('usuario')
        password = data.get('password')

        print(f"📌 Recibido: usuario={username}, contraseña={password}")
        
        user = User.get_user_by_credentials(username, password)

        print(f"🔍 Resultado de la consulta en MySQL: {user}")

        if user:
            # 🔹 Crear un token JWT con 1 hora de duración
            access_token = create_access_token(identity=user.username, expires_delta=timedelta(hours=1))

            response = jsonify({
                "message": "Login exitoso",
                "token": access_token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "rol": user.rol,
                    "sucursal_id": user.sucursal_id
                }
            })

            # 🔹 Permitir cookies en la respuesta
            #response.headers.add('Access-Control-Allow-Credentials', 'true')
            return response, 200

        return jsonify({"message": "Credenciales incorrectas"}), 401

    except Exception as e:
        print("❌ Error en login:", e)
        return jsonify({"message": "Error interno en el servidor"}), 500
