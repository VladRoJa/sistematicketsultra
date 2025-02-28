from werkzeug.security import check_password_hash
from app.models.database import get_db_connection

class User:
    def __init__(self, id, username, password, rol, id_sucursal):
        self.id = id
        self.username = username
        self.password = password
        self.rol = rol
        self.id_sucursal = id_sucursal

    @staticmethod
    def get_user_by_credentials(username, password):
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()

                # 🔹 Consulta corregida: solo selecciona las columnas necesarias
                query = "SELECT id, username, password, rol, id_sucursal FROM users WHERE username = LOWER(%s)"
                cursor.execute(query, (username,))
                result = cursor.fetchone()

                print(f"🔍 Resultado de la consulta: {result}")  # Depuración

                if result:
                    user_id, db_username, db_password, rol, id_sucursal = result

                    # ✅ Comparación de contraseña: Verifica si está encriptada o no
                    if db_password.startswith("$2b$") or db_password.startswith("$pbkdf2$"):
                        if check_password_hash(db_password, password):  
                            return User(user_id, db_username, db_password, rol, id_sucursal)
                    else:
                        if db_password == password:  
                            return User(user_id, db_username, db_password, rol, id_sucursal)

                print("❌ Usuario no encontrado o contraseña incorrecta")
                return None 

            except Exception as e:
                print(f"❌ Error en la consulta: {e}")
                return None
            finally:
                connection.close()
        else:
            return None

    @staticmethod
    def get_user_by_username(username):
        """ Método que faltaba en tu código """
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                
                query = "SELECT id, username, rol, id_sucursal FROM users WHERE username = LOWER(%s)"
                cursor.execute(query, (username,))
                result = cursor.fetchone()

                if result:
                    user_id, db_username, rol, id_sucursal = result
                    return User(user_id, db_username, None, rol, id_sucursal)  # No devolvemos la contraseña

                print("❌ Usuario no encontrado en get_user_by_username")
                return None  

            except Exception as e:
                print(f"❌ Error en get_user_by_username: {e}")
                return None
            finally:
                connection.close()
        else:
            return None
