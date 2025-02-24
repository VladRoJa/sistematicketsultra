# app/routes/ticket_routes.py
from flask import Blueprint, jsonify, request, session
from flask_cors import CORS
from app.models.database import get_db_connection
from app.models.ticket_model import Ticket
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from app.models.user_model import User


ticket_bp = Blueprint('tickets', __name__)

# Configuración de CORS para permitir solicitudes desde Angular
CORS(ticket_bp, resources={r"/*": {"origins": "http://localhost:4200"}}, 
     supports_credentials=True, allow_headers=["Content-Type", "Authorization"], 
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])   

# ✅ Ruta para obtener todos los tickets
@ticket_bp.route('/', methods=['GET'])
@jwt_required()
def get_tickets():
    try:
        # 🔹 Obtener usuario autenticado
        current_user = get_jwt_identity()
        user = User.get_user_by_username(current_user)

        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        sucursal_id = user.sucursal_id

        # 🔹 Si es admin (sucursal_id 1000), obtiene todos los tickets
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if sucursal_id == 1000:
            query = "SELECT id, titulo, descripcion, username, IF(estado='abierto', 'pendiente', estado) AS estado, fecha_creacion, fecha_finalizado FROM tickets"
            cursor.execute(query)
        else:
            query = "SELECT id, titulo, descripcion, username, IF(estado='abierto', 'pendiente', estado) AS estado, fecha_creacion, fecha_finalizado FROM tickets WHERE sucursal_id = %s"
            cursor.execute(query, (sucursal_id,))

        tickets = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": "Tickets cargados correctamente", "tickets": tickets}), 200

    except Exception as e:
        print(f"❌ Error al obtener tickets: {e}")
        return jsonify({"mensaje": f"Error al obtener tickets: {str(e)}"}), 500


# ✅ Ruta para crear un ticket
@ticket_bp.route('/', methods=['POST'])
def create_ticket():
    try:
        # 🔥 Verificar manualmente el token antes de @jwt_required()
        verify_jwt_in_request()
        
        auth_header = request.headers.get('Authorization')
        print(f"📌 Token recibido en Flask: {auth_header}")

        usuario_actual = get_jwt_identity()  # 🔹 Obtener usuario autenticado
        print(f"📌 Usuario autenticado en Flask: {usuario_actual}")  

        if usuario_actual is None:
            print("⚠️ No autorizado, sesión posiblemente expirada")
            return jsonify({"mensaje": "No autorizado"}), 401
        
        print(f"🔍 Verificando sesión en Flask: {session.get('user_id')}")

        data = request.get_json()
        titulo = data.get("titulo")
        descripcion = data.get("descripcion")

        if not titulo or not descripcion:
            print("❌ Error: Faltan datos obligatorios")
            return jsonify({"mensaje": "Faltan datos obligatorios"}), 400

        nuevo_ticket = Ticket.create_ticket(titulo, descripcion, usuario_actual)

        if nuevo_ticket:
            print("✅ Ticket creado exitosamente")
            return jsonify({"mensaje": "Ticket creado correctamente", "ticket": nuevo_ticket.to_dict()}), 201
        else:
            return jsonify({"mensaje": "Error al crear el ticket"}), 500

    except Exception as e:
        print(f"❌ Error en `create_ticket`: {e}")
        return jsonify({"mensaje": f"Error interno en el servidor: {str(e)}"}), 500
    
# ✅ Ruta para actualizar estado de un ticket
@ticket_bp.route('/update/<int:id>', methods=['PUT'])
@jwt_required()
def update_ticket_status(id):
    try:
        data = request.get_json()
        estado = data.get("estado")
        fecha_finalizado = data.get("fecha_finalizado") if estado == "finalizado" else None

        # 🔍 Verificar qué datos recibe Flask
        print(f"📌 Recibido en Flask: Ticket ID: {id}, Estado: {estado}, Fecha Finalizado: {fecha_finalizado}")

        if not estado:
            print("❌ Error: Estado es requerido")
            return jsonify({"mensaje": "Estado es requerido"}), 400

        # 🔍 Verificar si el ticket existe antes de actualizarlo
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tickets WHERE id = %s", (id,))
        ticket_existente = cursor.fetchone()

        if not ticket_existente:
            print(f"❌ Error: No existe el ticket con ID {id}")
            return jsonify({"mensaje": "El ticket no existe"}), 404

        # 🔹 Verificar si la fecha finalizado está en un formato válido
        if fecha_finalizado and not fecha_finalizado.endswith("Z"):
            print(f"⚠️ Advertencia: Fecha finalizado '{fecha_finalizado}' no tiene formato UTC")
        
        # 🔹 Intentar actualizar el ticket en la base de datos
        query = "UPDATE tickets SET estado = %s, fecha_finalizado = %s WHERE id = %s"
        cursor.execute(query, (estado, fecha_finalizado, id))
        conn.commit()

        cursor.close()
        conn.close()

        print(f"✅ Ticket {id} actualizado a '{estado}' con fecha '{fecha_finalizado}'")
        return jsonify({"mensaje": f"Ticket {id} actualizado a '{estado}' con fecha '{fecha_finalizado}'"}), 200

    except Exception as e:
        print(f"❌ Error al actualizar ticket {id}: {e}")
        return jsonify({"mensaje": f"Error al actualizar ticket: {str(e)}"}), 500

@ticket_bp.route('/', methods=['OPTIONS'])
def options_response():
    return '', 204  # Responder sin contenido, pero permitiendo la solicitud


@ticket_bp.route('/test-session', methods=['GET'])
@jwt_required()
def test_session():
    usuario_actual = get_jwt_identity()
    print(f"📌 Verificando sesión: {dict(session)}")
    return jsonify({
        "mensaje": "JWT sigue siendo válido",
        "usuario": usuario_actual
    }), 200