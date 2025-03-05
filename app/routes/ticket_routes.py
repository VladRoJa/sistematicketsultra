# app/routes/ticket_routes.py
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
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        data = request.get_json()
        titulo = data.get("titulo")
        descripcion = data.get("descripcion")
        departamento_id = data.get("departamento_id")

        if not titulo or not descripcion or not departamento_id:
            return jsonify({"mensaje": "Faltan datos obligatorios"}), 400

        nuevo_ticket = Ticket.create_ticket(titulo, descripcion, user.username, user.id_sucursal, departamento_id)

        if nuevo_ticket:
            return jsonify({"mensaje": "Ticket creado correctamente", "ticket": nuevo_ticket}), 201
        else:
            return jsonify({"mensaje": "Error al crear el ticket"}), 500

    except Exception as e:
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

        # 🔍 Verifica el estado recibido antes de actualizar
        print(f"📌 Estado recibido: '{estado}'")  

        if not estado:
            print("❌ Error: Estado no proporcionado")
            return jsonify({"mensaje": "Estado es requerido"}), 400

        # 🔍 Validar que el estado sea válido
        estados_validos = ["abierto", "en progreso", "finalizado"]
        if estado not in estados_validos:
            print(f"❌ Error: Estado '{estado}' no es válido. Opciones permitidas: {estados_validos}")
            return jsonify({"mensaje": "Estado no válido"}), 400

        # 🔍 Verificar si el ticket existe
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tickets WHERE id = %s", (id,))
        ticket_existente = cursor.fetchone()

        if not ticket_existente:
            print(f"❌ Error: No existe el ticket con ID {id}")
            return jsonify({"mensaje": "El ticket no existe o no se pudo actualizar"}), 404

        # 🔹 Intentar actualizar el estado
        query = "UPDATE tickets SET estado = %s WHERE id = %s"
        cursor.execute(query, (estado, id))
        conn.commit()

        cursor.close()
        conn.close()

        print(f"✅ Ticket {id} actualizado a '{estado}'")
        return jsonify({"mensaje": f"Ticket {id} actualizado a '{estado}'"}), 200

    except Exception as e:
        print(f"❌ Error al actualizar ticket {id}: {e}")
        return jsonify({"mensaje": f"Error al actualizar ticket: {str(e)}"}), 500


@ticket_bp.route("/all", methods=["GET", "OPTIONS"])
def all_tickets():
    return jsonify({"message": "Ruta /all funcionando correctamente"}), 200