# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\aparatos.py

# ------------------------------------------------------------------------------
# BLUEPRINT: Aparatos de Gimnasio
# ------------------------------------------------------------------------------

from flask import Blueprint, jsonify
from app.models.aparatos_model import AparatoGimnasio

aparatos_bp = Blueprint('aparatos', __name__, url_prefix='/api/aparatos')

# ------------------------------------------------------------------------------
# RUTA: Obtener aparatos por sucursal
# ------------------------------------------------------------------------------
@aparatos_bp.route('/<int:id_sucursal>', methods=['GET'])
def obtener_aparatos_por_sucursal(id_sucursal):
    """
    🔹 Devuelve todos los aparatos registrados para una sucursal específica.
    """
    try:
        aparatos = AparatoGimnasio.query.filter_by(id_sucursal=id_sucursal).all()

        resultado = [
            {
                'id': aparato.id,
                'codigo': aparato.codigo,
                'descripcion': aparato.descripcion,
                'marca': aparato.marca,
                'grupo_muscular': aparato.grupo_muscular,
                'categoria': aparato.categoria,
                'numero_equipo': aparato.numero_equipo
            }
            for aparato in aparatos
        ]

        return jsonify(resultado), 200

    except Exception as e:
        print(f"❌ Error al obtener aparatos: {e}")
        return jsonify({"mensaje": "Error interno al consultar aparatos"}), 500
