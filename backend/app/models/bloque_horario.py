# app/models/bloque_horario.py

from extensions import db

class BloqueHorario(db.Model):
    __tablename__ = 'bloques_horario'
    id = db.Column(db.Integer, primary_key=True)
    horario_general_id = db.Column(db.Integer, db.ForeignKey('horarios_generales.id'), nullable=False)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0=Domingo, 1=Lunes...
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)
    es_descanso = db.Column(db.Boolean, default=False)
