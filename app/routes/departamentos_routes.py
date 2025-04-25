#C:\Users\Vladimir\Documents\Sistema tickets\app\routes\departamentos_routes.py

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from app.models.database import get_db_connection

departamentos_bp = Blueprint('departamentos', __name__, url_prefix='/api/departamentos')

@departamentos_bp.route('/listar', methods=['GET'])
@jwt_required()
def listar_departamentos():
    """ 🔹 Devuelve la lista de departamentos desde la base de datos """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id, nombre FROM departamentos")
        departamentos = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({"departamentos": departamentos}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
