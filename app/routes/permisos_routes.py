# permisos_routes.py


from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.database import get_db_connection

permisos_bp = Blueprint('permisos', __name__, url_prefix='/api/permisos')

@permisos_bp.route('/asignar', methods=['POST'])
@jwt_required()
def asignar_permiso():
    """
    🔹 Asigna permisos a un usuario sobre un departamento.
    """
    try:
        current_user = get_jwt_identity()  # Usuario autenticado
        data = request.json
        user_id = data.get('user_id')
        departamento_id = data.get('departamento_id')
        es_admin = data.get('es_admin', False)

        if not user_id or not departamento_id:
            return jsonify({"error": "Faltan datos"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verificar si el usuario ya tiene permiso en ese departamento
        cursor.execute("""
            SELECT * FROM usuarios_permisos 
            WHERE user_id = %s AND departamento_id = %s
        """, (user_id, departamento_id))
        existe = cursor.fetchone()

        if existe:
            return jsonify({"error": "El usuario ya tiene este permiso"}), 400

        # Insertar nuevo permiso
        cursor.execute("""
            INSERT INTO usuarios_permisos (user_id, departamento_id, es_admin)
            VALUES (%s, %s, %s)
        """, (user_id, departamento_id, es_admin))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": "Permiso asignado correctamente"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@permisos_bp.route('/listar/<int:user_id>', methods=['GET'])
@jwt_required()
def listar_permisos(user_id):
    """
    🔹 Lista los permisos de un usuario.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT p.id, p.user_id, p.departamento_id, p.es_admin, d.nombre AS departamento
            FROM usuarios_permisos p
            JOIN departamentos d ON p.departamento_id = d.id
            WHERE p.user_id = %s
        """, (user_id,))
        
        permisos = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"permisos": permisos}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@permisos_bp.route('/eliminar', methods=['DELETE'])
@jwt_required()
def eliminar_permiso():
    """
    🔹 Elimina un permiso de un usuario.
    """
    try:
        data = request.json
        user_id = data.get('user_id')
        departamento_id = data.get('departamento_id')

        if not user_id or not departamento_id:
            return jsonify({"error": "Faltan datos"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM usuarios_permisos 
            WHERE user_id = %s AND departamento_id = %s
        """, (user_id, departamento_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": "Permiso eliminado correctamente"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@permisos_bp.route('/listar', methods=['GET'])
@jwt_required()
def listar_todos_los_permisos():
    """
    🔹 Lista todos los permisos de todos los usuarios.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT p.id, p.user_id, p.departamento_id, p.es_admin, d.nombre AS departamento
            FROM usuarios_permisos p
            JOIN departamentos d ON p.departamento_id = d.id
        """)
        
        permisos = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"permisos": permisos}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

