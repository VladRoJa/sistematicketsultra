# C:\Users\Vladimir\Documents\Sistema tickets\app\controllers\auth_controller.py

# -------------------------------------------------------------------------------
# CONTROLADOR DE AUTENTICACIÓN CON JWT
# -------------------------------------------------------------------------------

from flask import jsonify
from flask_jwt_extended import create_access_token
from app.models.user_model import UserORM
from datetime import timedelta

class AuthController:
    def login(self, data):
        """
        🔐 Inicia sesión y genera un token JWT.
        """
        try:
            username = data.get('username', '').strip().lower()
            password = data.get('password', '')

            print(f'🔐 Intentando iniciar sesión con usuario: {username}')

            user = UserORM.get_by_username(username)
            if user and user.verify_password(password):
                access_token = create_access_token(
                    identity=str(user.id),
                    expires_delta=timedelta(hours=1)
                )
                return jsonify({
                    'mensaje': 'Inicio de sesión exitoso',
                    'access_token': access_token,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'rol': user.rol,
                        'id_sucursal': user.id_sucursal
                    }
                }), 200

            print("❌ Credenciales inválidas")
            return jsonify({'mensaje': 'Credenciales inválidas'}), 401

        except Exception as e:
            print(f"❌ Error al iniciar sesión: {e}")
            return jsonify({'mensaje': 'Error al iniciar sesión'}), 500

    def logout(self):
        """
        🔓 Cierre de sesión (cliente borra su token, no el servidor).
        """
        return jsonify({'mensaje': 'Cierre de sesión exitoso (token debe eliminarse en el cliente)'}), 200

# -------------------------------------------------------------------------------
# INSTANCIA GLOBAL DEL CONTROLADOR
# -------------------------------------------------------------------------------

auth_controller = AuthController()
