# app/routes/horarios_routes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.models.horario_general import HorarioGeneral
from app.extensions import db

horarios_bp = Blueprint('horarios', __name__, url_prefix='/api/horarios')

@horarios_bp.route('/', methods=['GET'])
@jwt_required()
def listar_horarios():
    horarios = HorarioGeneral.query.all()
    data = [{"id": h.id, "nombre": h.nombre, "ciclo": h.ciclo} for h in horarios]
    return jsonify(data)

@horarios_bp.route('/', methods=['POST'])
@jwt_required()
def crear_horario():
    data = request.json
    horario = HorarioGeneral(nombre=data['nombre'], ciclo=data['ciclo'])
    db.session.add(horario)
    db.session.commit()
    return jsonify({"ok": True, "id": horario.id}), 201

@horarios_bp.route('/<int:id>', methods=['PUT'])
@jwt_required()
def editar_horario(id):
    horario = HorarioGeneral.query.get_or_404(id)
    data = request.json
    horario.nombre = data.get('nombre', horario.nombre)
    horario.ciclo = data.get('ciclo', horario.ciclo)
    db.session.commit()
    return jsonify({"ok": True})

@horarios_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def eliminar_horario(id):
    horario = HorarioGeneral.query.get_or_404(id)
    db.session.delete(horario)
    db.session.commit()
    return jsonify({"ok": True})
