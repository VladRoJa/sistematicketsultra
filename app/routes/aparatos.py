#C:\Users\Vladimir\Documents\Sistema tickets\app\routes\aparatos.py

from flask import Blueprint, jsonify
from app.models.database import get_db_connection

aparatos_bp = Blueprint('aparatos', __name__)

@aparatos_bp.route('/<int:id_sucursal>', methods=['GET'])
def obtener_aparatos_por_sucursal(id_sucursal):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
    SELECT id, codigo, id_sucursal, descripcion, marca, numero_equipo, grupo_muscular, categoria
    FROM aparatos_gimnasio
    WHERE id_sucursal = %s
    """
    cursor.execute(query, (id_sucursal,))
    resultados = cursor.fetchall()
    
    cursor.close()
    conn.close()

    return jsonify(resultados)
