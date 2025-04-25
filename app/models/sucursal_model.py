# C:\Users\Vladimir\Documents\Sistema tickets\app\models\sucursal_model.py

from app.extensions import db

class Sucursal(db.Model):
    __tablename__ = 'sucursales'

    id_sucursal = db.Column(db.Integer, primary_key=True)
    serie = db.Column(db.String(10))
    sucursal = db.Column(db.String(100))
    estado = db.Column(db.String(100))
    municipio = db.Column(db.String(100))
    direccion = db.Column(db.String(255))

    def __repr__(self):
        return f"<Sucursal {self.sucursal}>"
