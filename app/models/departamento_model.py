# C:\Users\Vladimir\Documents\Sistema tickets\app\models\departamento_model.py

# ------------------------------------------------------------------------------
# MODELO: DEPARTAMENTO
# ------------------------------------------------------------------------------

from app.extensions import db

class Departamento(db.Model):
    __tablename__ = 'departamentos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)

    # Relaciones (opcional, pero útil si se activan en Permisos)
    permisos = db.relationship('Permiso', backref='departamento', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Departamento {self.nombre}>"
