# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\permisos_routes.py

# ------------------------------------------------------------------------------
# BLUEPRINT: GESTIÓN DE PERMISOS DE USUARIOS A DEPARTAMENTOS
# ------------------------------------------------------------------------------

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.permiso_model import Permiso
from app.models.departamento_model import Departamento

permisos_bp = Blueprint('permisos', __name__, url_prefix='/api/permisos')

# ------------------------------------------------------------------------------
# RUTA: Asignar permiso a un usuario sobre un departamento
# ------------------------------------------------------------------------------
@permisos_bp.route('/asignar', methods=['POST'])
@jwt_required()
def asignar_permiso():
    try:
        data = request.json
        user_id = data.get('user_id')
        departamento_id = data.get('departamento_id')
        es_admin = data.get('es_admin', False)

        if not user_id or not departamento_id:
            return jsonify({"error": "Faltan datos"}), 400

        # Verificar si ya existe el permiso
        permiso_existente = Permiso.query.filter_by(user_id=user_id, departamento_id=departamento_id).first()
        if permiso_existente:
            return jsonify({"error": "El usuario ya tiene este permiso"}), 400

        permiso = Permiso(user_id=user_id, departamento_id=departamento_id, es_admin=es_admin)
        db.session.add(permiso)
        db.session.commit()

        return jsonify({"mensaje": "Permiso asignado correctamente"}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------------------
# RUTA: Listar permisos de un usuario específico
# ------------------------------------------------------------------------------
@permisos_bp.route('/listar/<int:user_id>', methods=['GET'])
@jwt_required()
def listar_permisos(user_id):
    try:
        permisos = Permiso.query.filter_by(user_id=user_id).all()
        resultado = [{
            "id": p.id,
            "user_id": p.user_id,
            "departamento_id": p.departamento_id,
            "es_admin": p.es_admin,
            "departamento": Departamento.query.get(p.departamento_id).nombre if p.departamento_id else "Desconocido"
        } for p in permisos]

        return jsonify({"permisos": resultado}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------------------
# RUTA: Eliminar un permiso específico
# ------------------------------------------------------------------------------
@permisos_bp.route('/eliminar', methods=['DELETE'])
@jwt_required()
def eliminar_permiso():
    try:
        data = request.json
        user_id = data.get('user_id')
        departamento_id = data.get('departamento_id')

        if not user_id or not departamento_id:
            return jsonify({"error": "Faltan datos"}), 400

        permiso = Permiso.query.filter_by(user_id=user_id, departamento_id=departamento_id).first()
        if not permiso:
            return jsonify({"error": "Permiso no encontrado"}), 404

        db.session.delete(permiso)
        db.session.commit()

        return jsonify({"mensaje": "Permiso eliminado correctamente"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------------------
# RUTA: Listar todos los permisos de todos los usuarios
# ------------------------------------------------------------------------------
@permisos_bp.route('/listar', methods=['GET'])
@jwt_required()
def listar_todos_los_permisos():
    try:
        permisos = Permiso.query.all()
        resultado = [{
            "id": p.id,
            "user_id": p.user_id,
            "departamento_id": p.departamento_id,
            "es_admin": p.es_admin,
            "departamento": Departamento.query.get(p.departamento_id).nombre if p.departamento_id else "Desconocido"
        } for p in permisos]

        return jsonify({"permisos": resultado}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
