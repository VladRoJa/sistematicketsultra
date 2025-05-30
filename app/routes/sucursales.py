# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\sucursales.py

# ------------------------------------------------------------------------------
# BLUEPRINT: SUCURSALES
# ------------------------------------------------------------------------------

from flask import Blueprint, jsonify
from app.models.sucursal_model import Sucursal
from app.utils.error_handler import manejar_error

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/api/sucursales')



# ------------------------------------------------------------------------------
# RUTA: Listar todas las sucursales
# ------------------------------------------------------------------------------
@sucursales_bp.route('/listar', methods=['GET'])
def listar_sucursales():
    try:
        sucursales = Sucursal.query.all()
        resultado = [
            {
                'sucursal_id': s.sucursal_id,
                'sucursal': s.sucursal
            } for s in sucursales
        ]
        return jsonify(resultado), 200
    except Exception as e:
        return manejar_error(e, "Listar sucursales")
