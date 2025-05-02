# C:\Users\Vladimir\Documents\Sistema tickets\scripts\crear_usuario_admin_interactivo.py

from app import create_app
from app.extensions import db
from app.models.user_model import UserORM
from werkzeug.security import generate_password_hash
import getpass

def crear_usuario_admin(username, password, id_sucursal=1000, department_id=1):
    app = create_app()
    with app.app_context():
        if UserORM.query.filter_by(username=username).first():
            print(f"❌ El usuario '{username}' ya existe.")
            return

        password_hash = generate_password_hash(password)

        admin = UserORM(
            username=username,
            password=password_hash,
            rol='ADMINISTRADOR',
            id_sucursal=id_sucursal,
            department_id=department_id
        )

        db.session.add(admin)
        db.session.commit()
        print(f"✅ Usuario administrador '{username}' creado exitosamente.")

if __name__ == "__main__":
    print("🚀 Creación de usuario administrador")

    username = input("👤 Usuario: ").strip()
    password = getpass.getpass("🔒 Contraseña: ").strip()
    id_sucursal_input = input("🏢 ID de Sucursal (default 1000): ").strip()
    department_id_input = input("🏢 ID de Departamento (default 1): ").strip()

    if not username or not password:
        print("⚠️ Debes ingresar un usuario y una contraseña válidos.")
    else:
        id_sucursal = int(id_sucursal_input) if id_sucursal_input else 1000
        department_id = int(department_id_input) if department_id_input else 1

        crear_usuario_admin(username, password, id_sucursal, department_id)
