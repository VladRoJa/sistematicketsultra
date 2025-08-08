# app/models/horario_general.py

from .. extensions import db

class HorarioGeneral(db.Model):
    __tablename__ = 'horarios_generales'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50))
    ciclo = db.Column(db.Integer, nullable=False)  # 1=Semana1, 2=Semana2

    bloques = db.relationship('BloqueHorario', backref='horario_general', cascade="all, delete-orphan")
