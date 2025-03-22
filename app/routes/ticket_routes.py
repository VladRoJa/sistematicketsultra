# app/routes/ticket_routes.py
from datetime import datetime
from flask import Blueprint, json, jsonify, request
from flask_cors import CORS
from app.models.database import get_db_connection
from app.models.ticket_model import Ticket
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user_model import User
import json  # Asegúrate de importar json para manipular historial_fechas

ticket_bp = Blueprint('tickets', __name__, url_prefix='/api/tickets')

# Configuración de CORS para permitir el acceso desde tu frontend
CORS(ticket_bp, resources={r"/*": {"origins": "http://localhost:4200"}},
     supports_credentials=True, allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# -----------------------------------------------------------------------------
# RUTA: Obtener todos los tickets
# -----------------------------------------------------------------------------
@ticket_bp.route('/all', methods=['GET'])
@jwt_required()
def get_tickets():
    try:
        current_user = get_jwt_identity()
        user = User.get_user_by_id(current_user)
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        limit = request.args.get('limit', default=15, type=int)
        offset = request.args.get('offset', default=0, type=int)

        conn = get_db_connection()

        # Primer cursor para la consulta principal
        cursor1 = conn.cursor(dictionary=True)
        
        if 1 <= user.id_sucursal <= 22:
            query = """SELECT * FROM tickets
                       WHERE id_sucursal = %s
                       ORDER BY fecha_creacion DESC
                       LIMIT %s OFFSET %s"""
            cursor1.execute(query, (user.id_sucursal, limit, offset))

            tickets = cursor1.fetchall()  # Consumir todos los resultados
            cursor1.close()

            # Segundo cursor para la consulta de conteo
            cursor2 = conn.cursor(dictionary=True)
            cursor2.execute("SELECT COUNT(*) as total FROM tickets WHERE id_sucursal = %s", (user.id_sucursal,))
            total_tickets = cursor2.fetchone()["total"]
            cursor2.close()

        elif user.id_sucursal == 100:
            if user.department_id is None:
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400

            query = """SELECT * FROM tickets
                       WHERE departamento_id = %s
                       ORDER BY fecha_creacion DESC
                       LIMIT %s OFFSET %s"""
            cursor1.execute(query, (user.department_id, limit, offset))

            tickets = cursor1.fetchall()
            cursor1.close()

            cursor2 = conn.cursor(dictionary=True)
            cursor2.execute("SELECT COUNT(*) as total FROM tickets WHERE departamento_id = %s", (user.department_id,))
            total_tickets = cursor2.fetchone()["total"]
            cursor2.close()

        elif user.id_sucursal == 1000:
            query = """SELECT * FROM tickets
                       ORDER BY fecha_creacion DESC
                       LIMIT %s OFFSET %s"""
            cursor1.execute(query, (limit, offset))

            tickets = cursor1.fetchall()
            cursor1.close()

            cursor2 = conn.cursor(dictionary=True)
            cursor2.execute("SELECT COUNT(*) as total FROM tickets")
            total_tickets = cursor2.fetchone()["total"]
            cursor2.close()
        else:
            cursor1.close()
            return jsonify({"mensaje": "Tipo de usuario no reconocido"}), 400

        conn.close()

        return jsonify({
            "mensaje": "Tickets cargados correctamente",
            "tickets": tickets,
            "total_tickets": total_tickets
        }), 200

    except Exception as e:
        print(f"❌ ERROR en get_tickets: {e}")
        return jsonify({"mensaje": f"Error al obtener tickets: {str(e)}"}), 500

# -----------------------------------------------------------------------------
# RUTA: Crear un ticket
# -----------------------------------------------------------------------------
@ticket_bp.route('/create', methods=['POST'])
@jwt_required()
def create_ticket():
    try:
        usuario_actual = get_jwt_identity()
        user = User.get_user_by_id(usuario_actual)

        if not user:
            print("❌ Usuario no encontrado en la base de datos")
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        data = request.get_json()
        print(f"📥 Datos recibidos: {data}")

        # Se esperan los siguientes datos para crear un ticket:
        descripcion = data.get("descripcion")
        departamento_id = data.get("departamento_id")
        criticidad = data.get("criticidad")
        categoria = data.get("categoria")

        # Validación de datos obligatorios
        if not descripcion or not departamento_id or not criticidad or not categoria:
            print("🚫 Faltan datos obligatorios")
            return jsonify({"mensaje": "Faltan datos obligatorios"}), 400

        # Crear el ticket utilizando el modelo Ticket
        nuevo_ticket = Ticket.create_ticket(descripcion, user.username, user.id_sucursal, departamento_id, criticidad, categoria)

        if nuevo_ticket:
            return jsonify({"mensaje": "Ticket creado correctamente", "ticket": nuevo_ticket}), 201
        else:
            print("❌ Error al insertar el ticket en la base de datos")
            return jsonify({"mensaje": "Error al crear el ticket"}), 500

    except Exception as e:
        print(f"❌ Excepción en create_ticket: {str(e)}")
        return jsonify({"mensaje": f"Error interno en el servidor: {str(e)}"}), 500

# -----------------------------------------------------------------------------
# RUTA: Actualizar estado de un ticket
# -----------------------------------------------------------------------------
@ticket_bp.route('/update/<int:id>', methods=['PUT'])
@jwt_required()
def update_ticket_status(id):
    try:
        print(f"🔍 Intentando actualizar el ticket con ID: {id}")
        if not id:
            return jsonify({"mensaje": "ID del ticket no proporcionado"}), 400

        data = request.get_json()
        estado = data.get("estado")
        fecha_solucion = data.get("fecha_solucion")  # Nueva fecha de solución (si aplica)
        historial_fechas = data.get("historial_fechas")  # Historial de cambios (si aplica)

        print(f"📌 Estado: {estado}, Fecha solución: {fecha_solucion}") 

        if not estado:
            print("❌ Error: Estado no proporcionado")
            return jsonify({"mensaje": "Estado es requerido"}), 400

        estados_validos = ["abierto", "en progreso", "finalizado"]
        if estado not in estados_validos:
            print(f"❌ Error: Estado '{estado}' no es válido.")
            return jsonify({"mensaje": "Estado no válido"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Obtener historial actual del ticket
        cursor.execute("SELECT historial_fechas FROM tickets WHERE id = %s", (id,))
        resultado = cursor.fetchone()
        historial_actual = json.loads(resultado["historial_fechas"]) if resultado and resultado["historial_fechas"] else []

        # Obtener el usuario que realiza la actualización
        usuario_actual_id = get_jwt_identity()
        usuario_actual = User.get_user_by_id(usuario_actual_id)
        
        # Si se proporciona fecha_solucion y es distinta, agregar registro al historial
        if fecha_solucion and (not historial_actual or historial_actual[-1]["fecha"] != fecha_solucion):
            nuevo_registro = {
                "fecha": fecha_solucion,
                "cambiadoPor": usuario_actual.username if usuario_actual else "Desconocido",
                "fechaCambio": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            historial_actual.append(nuevo_registro)

        # **NUEVO**: Verificar si el ticket ya está finalizado
        cursor.execute("SELECT estado, fecha_solucion FROM tickets WHERE id = %s", (id,))
        ticket_actual = cursor.fetchone()
        if ticket_actual and ticket_actual["estado"] == "finalizado":
            # Si ya está finalizado, se mantiene la fecha_solucion existente
            fecha_solucion = ticket_actual["fecha_solucion"]

        # Si el estado es "finalizado", asignar la fecha actual como fecha_finalizado
        fecha_finalizado = None
        if estado == "finalizado":
            fecha_finalizado = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Construir la consulta de actualización dinámicamente
        query = "UPDATE tickets SET estado = %s"
        values = [estado]

        if fecha_finalizado:
            query += ", fecha_finalizado = %s"
            values.append(fecha_finalizado)

        if fecha_solucion:
            query += ", fecha_solucion = %s"
            values.append(fecha_solucion)

        if historial_fechas:
            query += ", historial_fechas = %s"
            values.append(json.dumps(historial_actual))

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


# -----------------------------------------------------------------------------
# Ruta temporal para verificar la conexión
# -----------------------------------------------------------------------------
@ticket_bp.route("/all", methods=["GET", "OPTIONS"])
def all_tickets():
    return jsonify({"message": "Ruta /all funcionando correctamente"}), 200

# -----------------------------------------------------------------------------
# RUTA: Eliminar un ticket
# -----------------------------------------------------------------------------
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

        # Verificar que el ticket exista
        cursor.execute("SELECT * FROM tickets WHERE id = %s", (id,))
        ticket = cursor.fetchone()

        if not ticket:
            cursor.close()
            conn.close()
            return jsonify({"mensaje": "El ticket no existe"}), 404

        # Solo el creador del ticket o un administrador pueden eliminarlo
        if ticket["username"] != user.username and user.rol != "ADMINISTRADOR":
            cursor.close()
            conn.close()
            return jsonify({"mensaje": "No tienes permiso para eliminar este ticket"}), 403

        # Ejecutar la eliminación del ticket
        cursor.execute("DELETE FROM tickets WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": f"Ticket {id} eliminado correctamente"}), 200

    except Exception as e:
        return jsonify({"mensaje": f"Error interno en el servidor: {str(e)}"}), 500
