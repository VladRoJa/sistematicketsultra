# app/routes/bloques_routes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from ..models.bloque_horario import BloqueHorario
from .. extensions import db

bloques_bp = Blueprint('bloques', __name__, url_prefix='/api/bloques')

@bloques_bp.route('/<int:horario_general_id>', methods=['GET'])
@jwt_required()
def listar_bloques(horario_general_id):
    bloques = BloqueHorario.query.filter_by(horario_general_id=horario_general_id).all()
    data = [{
        "id": b.id,
        "dia_semana": b.dia_semana,
        "hora_inicio": b.hora_inicio.strftime('%H:%M'),
        "hora_fin": b.hora_fin.strftime('%H:%M'),
        "es_descanso": b.es_descanso
    } for b in bloques]
    return jsonify(data)

@bloques_bp.route('/', methods=['POST'])
@jwt_required()
def crear_bloque():
    data = request.json
    bloque = BloqueHorario(
        horario_general_id=data['horario_general_id'],
        dia_semana=data['dia_semana'],
        hora_inicio=data['hora_inicio'],  # formato "HH:MM"
        hora_fin=data['hora_fin'],
        es_descanso=data.get('es_descanso', False)
    )
    db.session.add(bloque)
    db.session.commit()
    return jsonify({"ok": True, "id": bloque.id}), 201

@bloques_bp.route('/<int:id>', methods=['PUT'])
@jwt_required()
def editar_bloque(id):
    bloque = BloqueHorario.query.get_or_404(id)
    data = request.json
    bloque.dia_semana = data.get('dia_semana', bloque.dia_semana)
    bloque.hora_inicio = data.get('hora_inicio', bloque.hora_inicio)
    bloque.hora_fin = data.get('hora_fin', bloque.hora_fin)
    bloque.es_descanso = data.get('es_descanso', bloque.es_descanso)
    db.session.commit()
    return jsonify({"ok": True})

@bloques_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def eliminar_bloque(id):
    bloque = BloqueHorario.query.get_or_404(id)
    db.session.delete(bloque)
    db.session.commit()
    return jsonify({"ok": True})
