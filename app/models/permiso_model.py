# C:\Users\Vladimir\Documents\Sistema tickets\app\models\permiso_model.py

# ------------------------------------------------------------------------------
# MODELO: PERMISOS DE USUARIOS SOBRE DEPARTAMENTOS
# ------------------------------------------------------------------------------

from app.extensions import db

class Permiso(db.Model):
    __tablename__ = 'usuarios_permisos'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'), nullable=False)
    es_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Relaciones (navegación futura, útil para joins y ORM avanzado)
    usuario = db.relationship('UserORM', backref='permisos')
    departamento = db.relationship('Departamento', backref='permisos')

    def __repr__(self):
        return f"<Permiso User {self.user_id} Departamento {self.departamento_id} Admin {self.es_admin}>"
