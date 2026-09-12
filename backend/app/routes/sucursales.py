# app\routes\sucursales.py

# ------------------------------------------------------------------------------
# BLUEPRINT: SUCURSALES
# ------------------------------------------------------------------------------

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from app.models.sucursal_model import Sucursal
from app.utils.error_handler import manejar_error
from app.utils.sucursal_audience import (
    SUCURSAL_AUDIENCE_OPERATIONAL,
    apply_sucursal_audience,
    normalize_sucursal_audience,
)

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/api/sucursales')


# ------------------------------------------------------------------------------
# RUTA: Listar sucursales por audiencia
# ------------------------------------------------------------------------------
@sucursales_bp.route('/listar', methods=['GET'])
@jwt_required()
def listar_sucursales():
    try:
        try:
            audience = normalize_sucursal_audience(
                request.args.get('audience'),
                default=SUCURSAL_AUDIENCE_OPERATIONAL,
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        query = apply_sucursal_audience(
            Sucursal.query,
            audience=audience,
        )
        sucursales = (
            query
            .order_by(Sucursal.is_demo.asc(), Sucursal.sucursal.asc())
            .all()
        )

        resultado = [
            {
                'sucursal_id': s.sucursal_id,
                'sucursal': s.sucursal,
                'serie': s.serie,
                'operational_status': s.operational_status,
                'is_demo': bool(s.is_demo),
            }
            for s in sucursales
        ]
        return jsonify(resultado), 200
    except Exception as e:
        return manejar_error(e, "Listar sucursales")
