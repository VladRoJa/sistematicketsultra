# app\routes\departamentos_routes.py

# ------------------------------------------------------------------------------
# BLUEPRINT: DEPARTAMENTOS
# ------------------------------------------------------------------------------

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from extensions import db
from sqlalchemy.exc import SQLAlchemyError
from utils.error_handler import manejar_error

# 🔹 Modelo
from ..models.departamento_model import Departamento

departamentos_bp = Blueprint('departamentos', __name__, url_prefix='/api/departamentos')

# ------------------------------------------------------------------------------
# RUTA: Listar departamentos
# ------------------------------------------------------------------------------
@departamentos_bp.route('/listar', methods=['GET'])
@jwt_required()
def listar_departamentos():
    """ 🔹 Devuelve la lista de departamentos registrados """
    try:
        departamentos = Departamento.query.with_entities(
            Departamento.id,
            Departamento.nombre
        ).all()

        resultado = [{"id": d.id, "nombre": d.nombre} for d in departamentos]

        return jsonify({"departamentos": resultado}), 200

    except SQLAlchemyError as e:
        return manejar_error(e, "listar_departamentos")
