# C:\Users\Vladimir\Documents\Sistema tickets\scripts\crear_usuario_admin.py

from app import create_app
from app.extensions import db
from app.models.user_model import UserORM
from werkzeug.security import generate_password_hash

def crear_usuario_admin(username, password, id_sucursal=1000, department_id=1):
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
            id_sucursal=id_sucursal,
            department_id=department_id
        )

        db.session.add(admin)
        db.session.commit()
        print(f"✅ Usuario administrador '{username}' creado exitosamente.")

if __name__ == "__main__":
    # 🔥 Aquí defines el primer admin
    crear_usuario_admin(
        username="admincorp",
        password="123"
    )
