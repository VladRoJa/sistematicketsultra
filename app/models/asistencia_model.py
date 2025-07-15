# app/models/asistencia_model.py
from app.extensions import db
from datetime import datetime

class RegistroAsistencia(db.Model):
    __tablename__ = 'registro_asistencia'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sucursal_id = db.Column(db.Integer, nullable=False)
    tipo_marcado = db.Column(db.String(20), nullable=False)  # entrada_m, salida_m, etc.
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Asistencia Usuario {self.usuario_id} - {self.tipo_marcado} @ {self.timestamp}>"
