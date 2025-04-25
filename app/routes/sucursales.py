# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\sucursales.py

from flask import Blueprint, jsonify
from app.models.sucursal_model import Sucursal

sucursales_bp = Blueprint('sucursales', __name__)
print("🏢 Blueprint sucursales_bp cargado correctamente")

@sucursales_bp.route('/listar', methods=['GET'])
def listar_sucursales():
    sucursales = Sucursal.query.all()
    resultado = [{
        'id_sucursal': s.id_sucursal,
        'sucursal': s.sucursal
    } for s in sucursales]
    return jsonify(resultado), 200
