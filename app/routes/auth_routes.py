#C:\Users\Vladimir\Documents\Sistema tickets\app\routes\auth_routes.py

from flask import Blueprint, request, jsonify
from flask_cors import CORS, cross_origin
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from app.models.user_model import User
from datetime import timedelta

auth_bp = Blueprint('auth', __name__)
CORS(auth_bp, resources={r"/*": {"origins": "http://localhost:4200"}}, supports_credentials=True)




### ✅ 🔹 OBTENER INFORMACIÓN DE LA SESIÓN
@cross_origin(origins="http://localhost:4200", supports_credentials=True)
@auth_bp.route('/session-info', methods=['GET', 'OPTIONS'])
@jwt_required()
def session_info():
    if request.method == 'OPTIONS':
        return '', 204  # ✅ Responde correctamente a preflight requests

    try:
        print(f"📡 Headers recibidos en session-info: {dict(request.headers)}")

        if not request.headers.get("Authorization"):
            return jsonify({"mensaje": "⚠️ No se recibió token en Authorization"}), 401

        current_user = get_jwt_identity()
        print(f"📌 Valor de get_jwt_identity(): {current_user}")

        try:
            user_id = int(current_user.strip())  
        except ValueError:
            print("❌ Error: El token no contiene un ID válido")
            return jsonify({"mensaje": "El token no contiene un ID válido"}), 401

        user = User.get_user_by_id(user_id)
        if not user:
            print("❌ Usuario no encontrado en la BD")
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        response = {
            "user": {
                "id": user.id,
                "username": user.username,
                "rol": user.rol,
                "id_sucursal": user.id_sucursal
            }
        }
        print(f"📡 Respuesta de session-info: {response}")

        return jsonify(response), 200  

    except Exception as e:
        print(f"❌ Error en session-info: {e}")
        return jsonify({"mensaje": f"Error en session-info: {str(e)}"}), 500


### ✅ 🔹 LOGIN (AUTENTICACIÓN JWT)
@auth_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 204  # ✅ Responde correctamente a preflight requests

    try:
        data = request.get_json()
        print("🔍 Datos recibidos:", data)  

        username = data.get('username').strip().lower()
        password = data.get('password')

        print(f"📌 Recibido: usuario={username}, contraseña={password}")

        user = User.get_user_by_credentials(username, password)
        print(f"🔍 Resultado de la consulta en MySQL: {user}")

        if user:
            access_token = create_access_token(identity=str(user.id).strip(), expires_delta=timedelta(hours=1))

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

