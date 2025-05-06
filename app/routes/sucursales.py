# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\sucursales.py

# ------------------------------------------------------------------------------
# BLUEPRINT: SUCURSALES
# ------------------------------------------------------------------------------

from flask import Blueprint, jsonify
from app.models.sucursal_model import Sucursal

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/api/sucursales')
print("🏢 Blueprint sucursales_bp cargado correctamente")


# ------------------------------------------------------------------------------
# RUTA: Listar todas las sucursales
# ------------------------------------------------------------------------------
@sucursales_bp.route('/listar', methods=['GET'])
def listar_sucursales():
    sucursales = Sucursal.query.all()
    resultado = [
        {
            'sucursal_id': s.sucursal_id,
            'sucursal': s.sucursal
        } for s in sucursales
    ]
    return jsonify(resultado), 200

