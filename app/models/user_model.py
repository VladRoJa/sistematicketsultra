# C:\Users\Vladimir\Documents\Sistema tickets\app\models\user_model.py

from werkzeug.security import check_password_hash
from app.extensions import db

# ─────────────────────────────────────────────────────────────
# MODELO: USUARIO
# ─────────────────────────────────────────────────────────────

class UserORM(db.Model):
    __tablename__ = 'users'

    # ─── Campos ──────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(50), default="usuario", nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)
    department_id = db.Column(db.Integer, nullable=False)

    # ─── Relaciones ─────────────────────────────────────────
    movimientos = db.relationship('MovimientoInventario', backref='usuario', cascade='all, delete-orphan')

    # ─────────────────────────────────────────────────────────────
    # MÉTODOS
    # ─────────────────────────────────────────────────────────────

    def verify_password(self, password_input):
        """Verifica si la contraseña ingresada es correcta."""
        print(f"🔐 Verificando contraseña para usuario: {self.username}")
        print(f"📦 Contraseña almacenada: {self.password}")
        print(f"🧾 Contraseña ingresada: {password_input}")

        if self.password.startswith("$2b$") or self.password.startswith("$pbkdf2$"):
            print("🔍 Usando check_password_hash")
            resultado = check_password_hash(self.password, password_input)
            print(f"✅ Resultado hash: {resultado}")
            return resultado

        resultado = self.password == password_input
        print(f"🔓 Comparación directa (texto plano): {resultado}")
        return resultado

    @classmethod
    def get_by_username(cls, username):
        user = cls.query.filter(db.func.lower(cls.username) == db.func.lower(username)).first()
        print(f"🔍 get_by_username({username}) → {user}")
        return user


    @classmethod
    def get_by_id(cls, user_id):
        """Obtiene un usuario por su ID."""
        return cls.query.filter_by(id=user_id).first()

    def __repr__(self):
        return f"<User {self.username}>"
    
