# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\ticket_routes.py
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file
from flask_cors import CORS
from app.models.database import get_db_connection
from app.models.ticket_model import Ticket
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user_model import User
import json  # Para manipular historial_fechas
from io import BytesIO
from openpyxl import Workbook  # Para la generación de archivos Excel
from openpyxl.styles import Font, Alignment, PatternFill

# Crear blueprint para tickets
ticket_bp = Blueprint('tickets', __name__, url_prefix='/api/tickets')

# Configuración de CORS para permitir el acceso desde el frontend (Angular)
CORS(ticket_bp, resources={r"/*": {"origins": "http://localhost:4200"}},
     supports_credentials=True, allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])


# -----------------------------------------------------------------------------
# RUTA: Obtener tickets con filtros (y sin paginación si se solicita)
# -----------------------------------------------------------------------------
@ticket_bp.route('/list', methods=['GET'])
@jwt_required()
def list_tickets_with_filters():
    """
    Devuelve tickets según filtros y según el tipo de usuario.
    - Permite filtrar por: estado, departamento_id y criticidad.
    - Si se envía el parámetro 'no_paging=true' en la URL, se omite la paginación (útil para exportación).
    - Si no se especifica 'no_paging', se aplican limit y offset para paginar.
    """
    try:
        # Obtener el usuario actual a partir del token JWT
        current_user = get_jwt_identity()
        user = User.get_user_by_id(current_user)
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        # Obtener parámetros de filtro desde la URL (si se envían)
        estado = request.args.get('estado')
        departamento_id = request.args.get('departamento_id')
        criticidad = request.args.get('criticidad')

        # Parámetro para omitir la paginación (para exportación masiva, por ejemplo)
        no_paging = request.args.get('no_paging', default='false').lower() == 'true'

        # Parámetros de paginación (limit y offset)
        limit = request.args.get('limit', default=15, type=int)
        offset = request.args.get('offset', default=0, type=int)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Construimos la query base (siempre verdadera para facilitar la concatenación)
        query = "SELECT * FROM tickets WHERE 1=1"
        values = []

        # Restricción según tipo de usuario
        if 1 <= user.id_sucursal <= 22:
            query += " AND id_sucursal = %s"
            values.append(user.id_sucursal)
        elif user.id_sucursal == 100:
            # Para supervisores se filtra por departamento
            if not user.department_id:
                cursor.close()
                conn.close()
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400
            query += " AND departamento_id = %s"
            values.append(user.department_id)
        elif user.id_sucursal == 1000:
            # Administrador global: no se filtra por sucursal
            pass
        else:
            cursor.close()
            conn.close()
            return jsonify({"mensaje": "Tipo de usuario no reconocido"}), 400

        # Agregar filtros dinámicos según parámetros recibidos
        if estado:
            query += " AND estado = %s"
            values.append(estado)
        if departamento_id:
            query += " AND departamento_id = %s"
            values.append(departamento_id)
        if criticidad:
            query += " AND criticidad = %s"
            values.append(criticidad)

        # Ordenar los tickets por fecha de creación descendente
        query += " ORDER BY fecha_creacion DESC"

        # Aplicar paginación solo si no se solicita exportación masiva
        if not no_paging:
            query += " LIMIT %s OFFSET %s"
            values.append(limit)
            values.append(offset)

        cursor.execute(query, tuple(values))
        tickets = cursor.fetchall()

        # Consulta para obtener el total de tickets filtrados (sin LIMIT/OFFSET)
        cursor2 = conn.cursor(dictionary=True)
        count_query = "SELECT COUNT(*) as total FROM tickets WHERE 1=1"
        count_vals = []

        # Repetir la restricción de usuario
        if 1 <= user.id_sucursal <= 22:
            count_query += " AND id_sucursal = %s"
            count_vals.append(user.id_sucursal)
        elif user.id_sucursal == 100 and user.department_id:
            count_query += " AND departamento_id = %s"
            count_vals.append(user.department_id)

        # Agregar filtros al conteo
        if estado:
            count_query += " AND estado = %s"
            count_vals.append(estado)
        if departamento_id:
            count_query += " AND departamento_id = %s"
            count_vals.append(departamento_id)
        if criticidad:
            count_query += " AND criticidad = %s"
            count_vals.append(criticidad)

        cursor2.execute(count_query, tuple(count_vals))
        total_tickets = cursor2.fetchone()["total"]
        cursor2.close()
        cursor.close()
        conn.close()

        return jsonify({
            "mensaje": "Tickets filtrados",
            "tickets": tickets,
            "total_tickets": total_tickets
        }), 200

    except Exception as e:
        print(f"❌ Error en list_tickets_with_filters: {e}")
        return jsonify({"mensaje": f"Error interno: {str(e)}"}), 500


# -----------------------------------------------------------------------------
# RUTA: Exportar tickets a Excel (con filtros aplicados)
# -----------------------------------------------------------------------------

@ticket_bp.route('/export-excel', methods=['GET'])
@jwt_required()
def export_excel():
    """
    Exporta todos los tickets (filtrados) en Excel:
    - Encabezados azules y negrita
    - Filtros activados
    - Encabezado congelado
    - Columnas alternadas blanco y gris
    - Separación de fecha y hora
    - Ajuste automático de columnas
    """
    try:
        from datetime import datetime
        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.worksheet.table import Table, TableStyleInfo

        current_user = get_jwt_identity()
        user = User.get_user_by_id(current_user)
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        # Filtros desde frontend
        estado = request.args.get('estado')
        departamento_id = request.args.get('departamento_id')
        criticidad = request.args.get('criticidad')
        username = request.args.get('username')
        categoria = request.args.get('categoria')
        descripcion = request.args.get('descripcion')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
                    SELECT 
                        t.*, 
                        d.nombre AS departamento,
                        a.codigo AS codigo_aparato
                    FROM tickets t
                    LEFT JOIN departamentos d ON t.departamento_id = d.id
                    LEFT JOIN aparatos_gimnasio a ON t.aparato_id = a.id

                """

        values = []

        # Filtro por tipo de usuario
        if 1 <= user.id_sucursal <= 22:
            query += " AND id_sucursal = %s"
            values.append(user.id_sucursal)
        elif user.id_sucursal == 100:
            if not user.department_id:
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400
            query += " AND departamento_id = %s"
            values.append(user.department_id)
        elif user.id_sucursal == 1000:
            pass
        else:
            return jsonify({"mensaje": "Tipo de usuario no reconocido"}), 400

        # Filtros
        if estado:
            query += " AND estado = %s"
            values.append(estado)
        if departamento_id:
            query += " AND departamento_id = %s"
            values.append(departamento_id)
        if criticidad:
            query += " AND criticidad = %s"
            values.append(criticidad)
        if username:
            query += " AND username = %s"
            values.append(username)
        if categoria:
            query += " AND categoria = %s"
            values.append(categoria)
        if descripcion:
            query += " AND descripcion LIKE %s"
            values.append(f"%{descripcion}%")

        query += " ORDER BY fecha_creacion DESC"
        cursor.execute(query, tuple(values))
        tickets = cursor.fetchall()

        wb = Workbook()
        ws = wb.active
        ws.title = "Tickets"

        # Estilos
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="0073C2")
        alt_fill = PatternFill("solid", fgColor="F2F2F2")

        headers = [
            "ID", "Descripción", "Usuario", "Estado", "Criticidad",
            "Fecha Creación", "Hora Creación", "Fecha Finalizado", "Hora Finalizado",
            "Fecha Solución", "Departamento", "Categoría", "Subcategoría", "Detalle",
            "Aparato ID", "Problema Detectado", "Requiere Refacción", "Descripción Refacción"
        ]
        ws.append(headers)

        for i, cell in enumerate(ws[1], 1):
            cell.font = header_font
            cell.fill = header_fill

        # Rellenar filas
        for idx, t in enumerate(tickets, start=2):
            fecha_creacion = t.get("fecha_creacion")
            fecha_finalizado = t.get("fecha_finalizado")
            fecha_solucion = t.get("fecha_solucion")

            ws.append([
                t.get("id", ""),
                t.get("descripcion", ""),
                t.get("username", ""),
                t.get("estado", ""),
                t.get("criticidad", ""),
                fecha_creacion.date() if fecha_creacion else "—",
                fecha_creacion.time().strftime("%H:%M:%S") if fecha_creacion else "—",
                fecha_finalizado.date() if fecha_finalizado else "—",
                fecha_finalizado.time().strftime("%H:%M:%S") if fecha_finalizado else "—",
                fecha_solucion.date() if fecha_solucion else "—",
                t.get("departamento", "—"),
                t.get("categoria", "—"),
                t.get("subcategoria", "—"),
                t.get("subsubcategoria", "—"),
                t.get("codigo_aparato", "—"),
                t.get("problema_detectado", "—"),
                "Sí" if t.get("necesita_refaccion") else "No",
                t.get("descripcion_refaccion", "—")
            ])

            # Alternar color de fondo
            if idx % 2 == 0:
                for cell in ws[idx]:
                    cell.fill = alt_fill

        # Ajustar ancho de columnas
        for column_cells in ws.columns:
            length = max(len(str(cell.value or "")) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = length + 2

        # Congelar encabezado
        ws.freeze_panes = "A2"

        # Activar filtros
        ws.auto_filter.ref = ws.dimensions

        # Guardar en buffer
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"tickets_exportados_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        )

    except Exception as e:
        print(f"❌ Error en export_excel: {e}")
        return jsonify({"mensaje": f"Error interno al exportar: {str(e)}"}), 500

# -----------------------------------------------------------------------------
# RUTA: Obtener todos los tickets (sin filtros, con paginación)
# -----------------------------------------------------------------------------
@ticket_bp.route('/all', methods=['GET'])
@jwt_required()
def get_tickets():
    """
    Devuelve todos los tickets sin filtros adicionales, aplicando paginación.
    """
    try:
        current_user = get_jwt_identity()
        user = User.get_user_by_id(current_user)
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        limit = request.args.get('limit', default=15, type=int)
        offset = request.args.get('offset', default=0, type=int)

        conn = get_db_connection()
        cursor1 = conn.cursor(dictionary=True)
        
        if 1 <= user.id_sucursal <= 22:
            query = """SELECT * FROM tickets
                       WHERE id_sucursal = %s
                       ORDER BY fecha_creacion DESC
                       LIMIT %s OFFSET %s"""
            cursor1.execute(query, (user.id_sucursal, limit, offset))
            tickets = cursor1.fetchall()
            cursor1.close()

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
# RUTA: Crear un nuevo ticket (POST)  
# -----------------------------------------------------------------------------  
@ticket_bp.route('/create', methods=['POST'])
@jwt_required()
def create_ticket():
    try:
        usuario_actual = get_jwt_identity()
        user = User.get_user_by_id(usuario_actual)
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        data = request.get_json()
        print(f"📥 Datos recibidos: {data}")

        descripcion = data.get("descripcion")
        departamento_id = data.get("departamento_id")
        criticidad = data.get("criticidad")
        categoria = data.get("categoria")
        subcategoria = data.get("subcategoria")
        subsubcategoria = data.get("subsubcategoria")

        # 🆕 Nuevos campos (solo para Mantenimiento - Aparatos)
        aparato_id = data.get("aparato_id")
        problema_detectado = data.get("problema_detectado")
        necesita_refaccion = data.get("necesita_refaccion")
        descripcion_refaccion = data.get("descripcion_refaccion")

        if not descripcion or not departamento_id or not criticidad or not categoria:
            return jsonify({"mensaje": "Faltan datos obligatorios"}), 400

        ticket_id = Ticket.create_ticket(
            descripcion=descripcion,
            username=user.username,
            id_sucursal=user.id_sucursal,
            departamento_id=departamento_id,
            criticidad=int(criticidad),
            categoria=categoria,
            subcategoria=subcategoria,
            subsubcategoria=subsubcategoria,
            aparato_id=aparato_id,
            problema_detectado=problema_detectado,
            necesita_refaccion=necesita_refaccion,
            descripcion_refaccion=descripcion_refaccion
        )

        if ticket_id:
            return jsonify({"mensaje": "Ticket creado correctamente", "ticket_id": ticket_id}), 201
        else:
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
    """
    Actualiza el estado de un ticket, y opcionalmente su fecha de solución.
    Además, gestiona el historial de cambios:
      - Si se recibe una nueva fecha_solucion, se agrega al historial.
      - Si el ticket ya está finalizado, se mantiene la fecha_solucion existente.
    """
    try:
        print(f"🔍 Intentando actualizar el ticket con ID: {id}")
        if not id:
            return jsonify({"mensaje": "ID del ticket no proporcionado"}), 400

        data = request.get_json()
        estado = data.get("estado")
        fecha_solucion = data.get("fecha_solucion")
        historial_fechas = data.get("historial_fechas")

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
        
        # Agregar al historial si se proporciona una nueva fecha de solución
        if fecha_solucion and (not historial_actual or historial_actual[-1]["fecha"] != fecha_solucion):
            nuevo_registro = {
                "fecha": fecha_solucion,
                "cambiadoPor": usuario_actual.username if usuario_actual else "Desconocido",
                "fechaCambio": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            historial_actual.append(nuevo_registro)

        # Si el ticket ya está finalizado, mantener la fecha_solucion existente
        cursor.execute("SELECT estado, fecha_solucion FROM tickets WHERE id = %s", (id,))
        ticket_actual = cursor.fetchone()
        if ticket_actual and ticket_actual["estado"] == "finalizado":
            fecha_solucion = ticket_actual["fecha_solucion"]

        # Si el estado es "finalizado", asignar la fecha actual como fecha_finalizado
        fecha_finalizado = None
        if estado == "finalizado":
            fecha_finalizado = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Construir la consulta de actualización
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
# RUTA: Eliminar un ticket
# -----------------------------------------------------------------------------
@ticket_bp.route('/delete/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_ticket(id):
    """
    Elimina el ticket especificado por su ID.
    Solo el creador del ticket o un administrador pueden eliminarlo.
    """
    try:
        usuario_actual = get_jwt_identity()
        user = User.get_user_by_id(usuario_actual)
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verificar que el ticket existe
        cursor.execute("SELECT * FROM tickets WHERE id = %s", (id,))
        ticket = cursor.fetchone()
        if not ticket:
            cursor.close()
            conn.close()
            return jsonify({"mensaje": "El ticket no existe"}), 404

        # Permitir eliminación solo si es el creador o un administrador
        if ticket["username"] != user.username and user.rol != "ADMINISTRADOR":
            cursor.close()
            conn.close()
            return jsonify({"mensaje": "No tienes permiso para eliminar este ticket"}), 403

        cursor.execute("DELETE FROM tickets WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": f"Ticket {id} eliminado correctamente"}), 200

    except Exception as e:
        return jsonify({"mensaje": f"Error interno en el servidor: {str(e)}"}), 500


# -----------------------------------------------------------------------------
# Ruta temporal para verificar la conexión
# -----------------------------------------------------------------------------
@ticket_bp.route("/all", methods=["GET", "OPTIONS"])
def all_tickets():
    return jsonify({"message": "Ruta /all funcionando correctamente"}), 200
