# app/models/user_model.py
from werkzeug.security import check_password_hash
from app.models.database import get_db_connection

class User:
    def __init__(self, id, username, password, rol, sucursal_id):
        self.id = id
        self.username = username
        self.password = password
        self.rol = rol
        self.sucursal_id = sucursal_id

    @staticmethod
    def get_user_by_credentials(username, password):
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()

                # 🔹 Consulta corregida: solo selecciona las 5 columnas necesarias
                query = "SELECT id, username, password, rol, sucursal_id FROM users WHERE username = %s"
                cursor.execute(query, (username,))
                result = cursor.fetchone()

                # 🔍 Depuración: Ver qué datos devuelve la consulta
                print(f"🔍 Resultado de la consulta: {result}")

                if result:
                    user_id, db_username, db_password, rol, sucursal_id = result  # 🔹 Corrección en la asignación

                    # ✅ Comparación de contraseña: Verifica si está encriptada o no
                    if db_password.startswith("$2b$") or db_password.startswith("$pbkdf2$"):  # Detectar si es bcrypt
                        if check_password_hash(db_password, password):  # 🔹 Comparar hash
                            return User(user_id, db_username, db_password, rol, sucursal_id)
                    else:
                        if db_password == password:  # 🔹 Comparar texto plano
                            return User(user_id, db_username, db_password, rol, sucursal_id)

                return None  # No se encontró el usuario o la contraseña es incorrecta

            except Exception as e:
                print(f"❌ Error en la consulta: {e}")
                return None
            finally:
                connection.close()
        else:
            return None

    @staticmethod
    def get_user_by_username(username):
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()

                query = "SELECT id, username, rol, sucursal_id FROM users WHERE username = %s"
                cursor.execute(query, (username,))
                result = cursor.fetchone()

                if result:
                    user_id, db_username, rol, sucursal_id = result
                    return User(user_id, db_username, None, rol, sucursal_id)  # No devolvemos la contraseña

                return None  # Usuario no encontrado

            except Exception as e:
                print(f"❌ Error en get_user_by_username: {e}")
                return None
            finally:
                connection.close()
        else:
            return None
