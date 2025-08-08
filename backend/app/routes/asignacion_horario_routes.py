# app/routes/asignacion_horario_routes.py
from flask import Blueprint, request, jsonify
from backend.app.models.empleado_horario_asignado import EmpleadoHorarioAsignado
from backend.app.models.horario_general import HorarioGeneral
from backend.app.models.user_model import UserORM
from backend.app. extensions import db
from datetime import date
from flask_jwt_extended import jwt_required

asignacion_bp = Blueprint('asignacion', __name__, url_prefix='/api/asignaciones')

@asignacion_bp.route('/empleado/<int:usuario_id>', methods=['GET'])
@jwt_required()
def listar_asignaciones(usuario_id):
    asignaciones = EmpleadoHorarioAsignado.query.filter_by(usuario_id=usuario_id).all()
    data = [{
        "id": a.id,
        "usuario_id": a.usuario_id,
        "horario_general_id": a.horario_general_id,
        "fecha_inicio": a.fecha_inicio.strftime('%Y-%m-%d') if a.fecha_inicio else None,
        "activo": a.activo
    } for a in asignaciones]
    return jsonify(data)

@asignacion_bp.route('/', methods=['POST'])
@jwt_required()
def asignar_horario():
    data = request.json
    usuario_id = data['usuario_id']
    horario_general_id = data['horario_general_id']
    fecha_inicio = data.get('fecha_inicio', date.today().isoformat())
    # Opcional: inactiva todas las asignaciones previas
    EmpleadoHorarioAsignado.query.filter_by(usuario_id=usuario_id, activo=True).update({'activo': False})
    asignacion = EmpleadoHorarioAsignado(
        usuario_id=usuario_id,
        horario_general_id=horario_general_id,
        fecha_inicio=fecha_inicio,
        activo=True
    )
    db.session.add(asignacion)
    db.session.commit()
    return jsonify({"ok": True, "id": asignacion.id}), 201

@asignacion_bp.route('/<int:id>', methods=['PUT'])
@jwt_required()
def editar_asignacion(id):
    asignacion = EmpleadoHorarioAsignado.query.get_or_404(id)
    data = request.json
    asignacion.horario_general_id = data.get('horario_general_id', asignacion.horario_general_id)
    asignacion.fecha_inicio = data.get('fecha_inicio', asignacion.fecha_inicio)
    asignacion.activo = data.get('activo', asignacion.activo)
    db.session.commit()
    return jsonify({"ok": True})

@asignacion_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def eliminar_asignacion(id):
    asignacion = EmpleadoHorarioAsignado.query.get_or_404(id)
    db.session.delete(asignacion)
    db.session.commit()
    return jsonify({"ok": True})
