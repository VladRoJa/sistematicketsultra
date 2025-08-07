# app/models/formulario_ticket.py

from extensions import db

class FormularioTicket(db.Model):
    __tablename__ = 'formulario_ticket'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'), nullable=False)
    tipo_reporte = db.Column(db.String(50), nullable=True)
    activo = db.Column(db.Boolean, default=True)
    campos = db.relationship('CampoFormulario', backref='formulario', cascade='all, delete-orphan')

class CampoFormulario(db.Model):
    __tablename__ = 'campo_formulario'
    id = db.Column(db.Integer, primary_key=True)
    formulario_id = db.Column(db.Integer, db.ForeignKey('formulario_ticket.id'), nullable=False)
    nombre_campo = db.Column(db.String(50), nullable=False)
    etiqueta = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    obligatorio = db.Column(db.Boolean, default=False)
    orden = db.Column(db.Integer, default=1)
    opciones = db.Column(db.Text, nullable=True)
    referencia_arbol = db.Column(db.Boolean, default=False)
    referencia_inventario = db.Column(db.Boolean, default=False)
    solo_si_nivel = db.Column(db.Integer, nullable=True)
