# app/models/empleado_horario_asignado.py

from .. extensions import db

class EmpleadoHorarioAsignado(db.Model):
    __tablename__ = 'empleado_horario_asignado'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    horario_general_id = db.Column(db.Integer, db.ForeignKey('horarios_generales.id'), nullable=False)
    fecha_inicio = db.Column(db.Date)
    activo = db.Column(db.Boolean, default=True)
