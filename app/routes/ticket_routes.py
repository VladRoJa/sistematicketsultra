# app/routes/ticket_routes.py
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_cors import CORS
from app.models.database import get_db_connection
from app.models.ticket_model import Ticket
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user_model import User




ticket_bp = Blueprint('tickets', __name__, url_prefix='/api/tickets')



# Configuración de CORS
CORS(ticket_bp, resources={r"/*": {"origins": "http://localhost:4200"}}, 
     supports_credentials=True, allow_headers=["Content-Type", "Authorization"], 
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# ✅ Ruta para obtener todos los tickets
@ticket_bp.route('/all', methods=['GET'])
@jwt_required()
def get_tickets():
    try:
        current_user = get_jwt_identity()
        user = User.get_user_by_id(current_user)

        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        id_sucursal = user.id_sucursal

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if user.rol in ["ADMINISTRADOR", "TECNICO"]:
            query = "SELECT * FROM tickets"
            cursor.execute(query)
        else:
            query = "SELECT * FROM tickets WHERE id_sucursal = %s"
            cursor.execute(query, (id_sucursal,))

        tickets = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": "Tickets cargados correctamente", "tickets": tickets}), 200

    except Exception as e:
        return jsonify({"mensaje": f"Error al obtener tickets: {str(e)}"}), 500


# ✅ Ruta para crear un ticket
@ticket_bp.route('/create', methods=['POST'])
@jwt_required()
def create_ticket():
    try:
        usuario_actual = get_jwt_identity()
        user = User.get_user_by_id(usuario_actual)

        if not user:
            print("❌ Usuario no encontrado en la base de datos")  # 🔍 Verificar si el usuario no se encuentra en la base de datos
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        data = request.get_json()
        print(f"📥 Datos recibidos: {data}")  # 🔍 Ver qué datos llegan al backend
        
        titulo = data.get("titulo")
        descripcion = data.get("descripcion")
        departamento_id = data.get("departamento_id")
        criticidad = data.get("criticidad")
        categoria = data.get("categoria")

        if not titulo or not descripcion or not departamento_id or not criticidad or not categoria:
            print("🚫 Faltan datos obligatorios")  # 🔍 Verificar si faltan datos
            return jsonify({"mensaje": "Faltan datos obligatorios"}), 400

        nuevo_ticket = Ticket.create_ticket(titulo, descripcion, user.username, user.id_sucursal, departamento_id, criticidad, categoria)

        if nuevo_ticket:
            return jsonify({"mensaje": "Ticket creado correctamente", "ticket": nuevo_ticket}), 201
        else:
            print("❌ Error al insertar el ticket en la base de datos")
            return jsonify({"mensaje": "Error al crear el ticket"}), 500

    except Exception as e:
        print(f"❌ Excepción en create_ticket: {str(e)}")  # 🔍 Capturar el error exacto
        return jsonify({"mensaje": f"Error interno en el servidor: {str(e)}"}), 500


# ✅ Ruta para actualizar estado de un ticket
@ticket_bp.route('/update/<int:id>', methods=['PUT'])
@jwt_required()
def update_ticket_status(id):
    try:
        print(f"🔍 Intentando actualizar el ticket con ID: {id}")

        if not id:
            return jsonify({"mensaje": "ID del ticket no proporcionado"}), 400

        data = request.get_json()
        estado = data.get("estado")

        print(f"📌 Estado recibido: '{estado}'")  

        if not estado:
            print("❌ Error: Estado no proporcionado")
            return jsonify({"mensaje": "Estado es requerido"}), 400

        estados_validos = ["abierto", "en progreso", "finalizado"]
        if estado not in estados_validos:
            print(f"❌ Error: Estado '{estado}' no es válido.")
            return jsonify({"mensaje": "Estado no válido"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Obtener la fecha si el estado es finalizado
        fecha_finalizado = None
        if estado == "finalizado":
            fecha_finalizado = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 🔹 Actualizar el estado y la fecha si aplica
        query = "UPDATE tickets SET estado = %s"
        values = [estado]

        if fecha_finalizado:
            query += ", fecha_finalizado = %s"
            values.append(fecha_finalizado)

        query += " WHERE id = %s"
        values.append(id)

        cursor.execute(query, tuple(values))
        conn.commit()

        cursor.close()
        conn.close()

        print(f"✅ Ticket {id} actualizado a '{estado}' con fecha de finalización: {fecha_finalizado}")
        return jsonify({"mensaje": f"Ticket {id} actualizado"}), 200

    except Exception as e:
        print(f"❌ Error al actualizar ticket {id}: {e}")
        return jsonify({"mensaje": f"Error al actualizar ticket: {str(e)}"}), 500


@ticket_bp.route("/all", methods=["GET", "OPTIONS"])
def all_tickets():
    return jsonify({"message": "Ruta /all funcionando correctamente"}), 200

# ✅ Ruta para eliminar un ticket
@ticket_bp.route('/delete/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_ticket(id):
    try:
        usuario_actual = get_jwt_identity()
        user = User.get_user_by_id(usuario_actual)

        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verificar si el ticket existe
        cursor.execute("SELECT * FROM tickets WHERE id = %s", (id,))
        ticket = cursor.fetchone()

        if not ticket:
            cursor.close()
            conn.close()
            return jsonify({"mensaje": "El ticket no existe"}), 404

        # Solo puede eliminar el creador del ticket o un administrador
        if ticket["username"] != user.username and user.rol != "ADMINISTRADOR":
            cursor.close()
            conn.close()
            return jsonify({"mensaje": "No tienes permiso para eliminar este ticket"}), 403

        # Eliminar el ticket
        cursor.execute("DELETE FROM tickets WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": f"Ticket {id} eliminado correctamente"}), 200

    except Exception as e:
        return jsonify({"mensaje": f"Error interno en el servidor: {str(e)}"}), 500
