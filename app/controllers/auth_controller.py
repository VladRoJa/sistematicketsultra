#auth_controller.py

from flask import jsonify, session
from app.models.user_model import User

class AuthController:
    def login(self, data):
        try:
            username = data.get('username')
            password = data.get('password')

            print(f'Intentando iniciar sesión con usuario: {username} y contraseña: {password}')

            user = User.get_user_by_credentials(username, password)
            if user:
                session['user_id'] = user.id
                session['rol'] = user.rol
                session['id_sucursal'] = user.id_sucursal
                session['username'] = user.username
                return jsonify({
                    'mensaje': 'Inicio de sesión exitoso',
                    'rol': user.rol,
                    'username': user.username,
                    'id_sucursal': user.id_sucursal,
                }), 200
            else:
                print("Credenciales inválidas")
                return jsonify({'mensaje': 'Credenciales inválidas'}), 401
        except Exception as e:
            print(f"Error al iniciar sesión: {e}")
            return jsonify({'mensaje': 'Error al iniciar sesión'}), 500

    def logout(self):
        session.pop('user_id', None)
        session.pop('rol', None)
        session.pop('id_sucursal', None)
        return jsonify({'mensaje': 'Cierre de sesión exitoso'}), 200

# Crea una instancia de la clase
auth_controller = AuthController()