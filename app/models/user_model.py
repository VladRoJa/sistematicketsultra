#user_model.py

from werkzeug.security import check_password_hash
from app.models.database import get_db_connection

class User:
    def __init__(self, id, username, password, rol="usuario", id_sucursal=None, department_id=None):
        self.id = id
        self.username = username
        self.password = password
        self.rol = rol if rol else "usuario"
        self.id_sucursal = id_sucursal
        self.department_id = department_id  # Nuevo campo

    @staticmethod
    def get_user_by_credentials(username, password):
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                query = """
                    SELECT id, username, password, rol, id_sucursal, department_id 
                    FROM users 
                    WHERE username = LOWER(%s)
                """
                cursor.execute(query, (username,))
                result = cursor.fetchone()

                if result:
                    user_id, db_username, db_password, rol, id_sucursal, department_id = result

                    # Verificación de contraseña usando hash (si corresponde)
                    if db_password.startswith("$2b$") or db_password.startswith("$pbkdf2$"):
                        if not check_password_hash(db_password, password):
                            return None
                    elif db_password != password:
                        return None

                    return User(user_id, db_username, db_password, rol, id_sucursal, department_id)

                return None
            except Exception as e:
                print(f"❌ Error en la autenticación: {e}")
                return None
            finally:
                connection.close()

    @staticmethod
    def get_user_by_username(username):
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                query = """
                    SELECT id, username, rol, id_sucursal, department_id 
                    FROM users 
                    WHERE username = LOWER(%s)
                """
                cursor.execute(query, (username,))
                result = cursor.fetchone()

                if result:
                    user_id, db_username, rol, id_sucursal, department_id = result
                    return User(user_id, db_username, None, rol, id_sucursal, department_id)

                print("❌ Usuario no encontrado en get_user_by_username")
                return None
            except Exception as e:
                print(f"❌ Error en get_user_by_username: {e}")
                return None
            finally:
                connection.close()
        else:
            return None

    @staticmethod
    def get_user_by_id(user_id):
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                query = """
                    SELECT id, username, rol, id_sucursal, department_id 
                    FROM users 
                    WHERE id = %s
                """
                cursor.execute(query, (user_id,))
                result = cursor.fetchone()

                if result:
                    user_id, username, rol, id_sucursal, department_id = result
                    return User(user_id, username, None, rol, id_sucursal, department_id)

                return None
            except Exception as e:
                print(f"❌ Error en get_user_by_id: {e}")
                return None
            finally:
                connection.close()
        else:
            return None
