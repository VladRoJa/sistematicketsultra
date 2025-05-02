# C:\Users\Vladimir\Documents\Sistema tickets\app\models\aparatos_model.py

# ------------------------------------------------------------------------------
# MODELO: Aparatos de Gimnasio
# ------------------------------------------------------------------------------

from app.extensions import db

class AparatoGimnasio(db.Model):
    __tablename__ = 'aparatos_gimnasio'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), nullable=False)
    id_sucursal = db.Column(db.Integer, db.ForeignKey('sucursales.id_sucursal'), nullable=False)
    descripcion = db.Column(db.String(255))
    marca = db.Column(db.String(100))
    grupo_muscular = db.Column(db.String(100))
    categoria = db.Column(db.String(100))
    numero_equipo = db.Column(db.String(50))

    def __repr__(self):
        return f"<AparatoGimnasio {self.codigo} - Sucursal {self.id_sucursal}>"

