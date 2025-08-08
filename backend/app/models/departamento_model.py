# app\models\departamento_model.py

# ------------------------------------------------------------------------------
# MODELO: DEPARTAMENTO
# ------------------------------------------------------------------------------

from .. extensions import db

class Departamento(db.Model):
    __tablename__ = 'departamentos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)


    def __repr__(self):
        return f"<Departamento {self.nombre}>"

