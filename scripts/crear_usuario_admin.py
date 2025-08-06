# scripts\crear_usuario_admin.py

from app import create_app
from app.extensions import db
from app.models.user_model import UserORM
from werkzeug.security import generate_password_hash
import os
from getpass import getpass

def crear_usuario_admin(username, password, sucursal_id=1000, department_id=1):
    app = create_app()
    with app.app_context():
        # Verificar si el usuario ya existe
        if UserORM.query.filter_by(username=username).first():
            print(f"❌ El usuario '{username}' ya existe.")
            return

        # Crear usuario nuevo
        password_hash = generate_password_hash(password)

        admin = UserORM(
            username=username,
            password=password_hash,
            rol='ADMINISTRADOR',
            sucursal_id=sucursal_id,
            department_id=department_id
        )

        db.session.add(admin)
        db.session.commit()
        print(f"✅ Usuario administrador '{username}' creado exitosamente.")

if __name__ == "__main__":
    username = "admincorp"
    # 1. Intenta leer la contraseña de variable de entorno
    password = os.getenv("ADMIN_PASSWORD")
    # 2. Si no existe, pide al usuario que la ingrese (con prompt seguro)
    if not password:
        password = getpass("Introduce la contraseña para el usuario admincorp: ")
    # 3. Valida que la contraseña tenga al menos 8 caracteres (ajusta a tu política)
    if not password or len(password) < 8:
        raise ValueError("La contraseña de admin debe tener mínimo 8 caracteres.")
    crear_usuario_admin(
        username=username,
        password=password
    )
