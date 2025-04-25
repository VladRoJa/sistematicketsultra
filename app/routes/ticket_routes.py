# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\ticket_routes.py

from flask import Blueprint, jsonify, request, send_file
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import or_

from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.extensions import db

# ─────────────────────────────────────────────────────────────
# BLUEPRINT: TICKETS
# ─────────────────────────────────────────────────────────────
ticket_bp = Blueprint('tickets', __name__, url_prefix='/api/tickets')

CORS(ticket_bp, resources={r"/*": {"origins": "http://localhost:4200"}},
     supports_credentials=True, allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])


# ─────────────────────────────────────────────────────────────
# RUTA: Crear ticket
# ─────────────────────────────────────────────────────────────
@ticket_bp.route('/create', methods=['POST'])
@jwt_required()
def create_ticket():
    try:
        usuario_actual = get_jwt_identity()
        user = UserORM.get_by_id(usuario_actual)
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        data = request.get_json()

        descripcion = data.get("descripcion")
        departamento_id = data.get("departamento_id")
        criticidad = data.get("criticidad")
        categoria = data.get("categoria")
        subcategoria = data.get("subcategoria")
        subsubcategoria = data.get("subsubcategoria")
        aparato_id = data.get("aparato_id")
        problema_detectado = data.get("problema_detectado")
        necesita_refaccion = data.get("necesita_refaccion", False)
        descripcion_refaccion = data.get("descripcion_refaccion")

        if not descripcion or not departamento_id or not criticidad or not categoria:
            return jsonify({"mensaje": "Faltan datos obligatorios"}), 400

        nuevo_ticket = Ticket.create_ticket(
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

        return jsonify({
            "mensaje": "Ticket creado correctamente",
            "ticket_id": nuevo_ticket.id
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"mensaje": f"Error interno: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────
# RUTA: Obtener todos los tickets (paginados) - SIMPLE
# ─────────────────────────────────────────────────────────────
@ticket_bp.route('/all', methods=['GET'])
@jwt_required()
def get_tickets():
    try:
        user = UserORM.get_by_id(get_jwt_identity())
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        limit = request.args.get('limit', default=15, type=int)
        offset = request.args.get('offset', default=0, type=int)

        query = Ticket.query

        if 1 <= user.id_sucursal <= 22:
            query = query.filter_by(id_sucursal=user.id_sucursal)
        elif user.id_sucursal == 100:
            if user.department_id is None:
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400
            query = query.filter_by(departamento_id=user.department_id)
        elif user.id_sucursal != 1000:
            return jsonify({"mensaje": "Tipo de usuario no reconocido"}), 400

        total_tickets = query.count()
        tickets = query.order_by(Ticket.fecha_creacion.desc()).limit(limit).offset(offset).all()

        return jsonify({
            "mensaje": "Tickets cargados correctamente",
            "tickets": [t.to_dict() for t in tickets],
            "total_tickets": total_tickets
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"mensaje": f"Error interno: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────
# RUTA: Obtener tickets con filtros dinámicos
# ─────────────────────────────────────────────────────────────
@ticket_bp.route('/list', methods=['GET'])
@jwt_required()
def list_tickets_with_filters():
    try:
        user = UserORM.get_by_id(get_jwt_identity())
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        estado = request.args.get('estado')
        departamento_id = request.args.get('departamento_id')
        criticidad = request.args.get('criticidad')
        no_paging = request.args.get('no_paging', default='false').lower() == 'true'
        limit = request.args.get('limit', default=15, type=int)
        offset = request.args.get('offset', default=0, type=int)

        query = Ticket.query

        if 1 <= user.id_sucursal <= 22:
            query = query.filter_by(id_sucursal=user.id_sucursal)
        elif user.id_sucursal == 100:
            if not user.department_id:
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400
            query = query.filter_by(departamento_id=user.department_id)
        elif user.id_sucursal != 1000:
            return jsonify({"mensaje": "Tipo de usuario no reconocido"}), 400

        if estado:
            query = query.filter_by(estado=estado)
        if departamento_id:
            query = query.filter_by(departamento_id=int(departamento_id))
        if criticidad:
            query = query.filter_by(criticidad=int(criticidad))

        total_tickets = query.count()
        if not no_paging:
            query = query.limit(limit).offset(offset)

        tickets = query.order_by(Ticket.fecha_creacion.desc()).all()

        return jsonify({
            "mensaje": "Tickets filtrados",
            "tickets": [t.to_dict() for t in tickets],
            "total_tickets": total_tickets
        }), 200

    except Exception as e:
        return jsonify({"mensaje": f"Error interno: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────
# RUTA: Actualizar estado de un ticket
# ─────────────────────────────────────────────────────────────
@ticket_bp.route('/update/<int:id>', methods=['PUT'])
@jwt_required()
def update_ticket_status(id):
    try:
        ticket = Ticket.query.get(id)
        if not ticket:
            return jsonify({"mensaje": "Ticket no encontrado"}), 404

        data = request.get_json()
        estado = data.get("estado")
        fecha_solucion = data.get("fecha_solucion")
        historial_fechas = data.get("historial_fechas")

        if not estado:
            return jsonify({"mensaje": "Estado es requerido"}), 400

        ticket.estado = estado
        if estado == "finalizado":
            ticket.fecha_finalizado = datetime.utcnow()
        if fecha_solucion:
            ticket.fecha_solucion = datetime.strptime(fecha_solucion, '%Y-%m-%d')
        ticket.historial_fechas = historial_fechas

        db.session.commit()
        return jsonify({"mensaje": f"Ticket {id} actualizado correctamente"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"mensaje": f"Error interno: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────
# RUTA: Eliminar ticket
# ─────────────────────────────────────────────────────────────
@ticket_bp.route('/delete/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_ticket(id):
    try:
        ticket = Ticket.query.get(id)
        if not ticket:
            return jsonify({"mensaje": "El ticket no existe"}), 404

        usuario_actual_id = get_jwt_identity()
        usuario_actual = UserORM.get_by_id(usuario_actual_id)

        if ticket.username != usuario_actual.username and usuario_actual.rol != "ADMINISTRADOR":
            return jsonify({"mensaje": "No tienes permiso para eliminar este ticket"}), 403

        db.session.delete(ticket)
        db.session.commit()

        return jsonify({"mensaje": f"Ticket {id} eliminado correctamente"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"mensaje": f"Error interno: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────
# RUTA: Exportar tickets a Excel
# ─────────────────────────────────────────────────────────────
@ticket_bp.route('/export-excel', methods=['GET'])
@jwt_required()
def export_excel():
    try:
        user = UserORM.get_by_id(get_jwt_identity())
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        estado = request.args.get('estado')
        departamento_id = request.args.get('departamento_id')
        criticidad = request.args.get('criticidad')
        username = request.args.get('username')
        categoria = request.args.get('categoria')
        descripcion = request.args.get('descripcion')

        query = Ticket.query

        if 1 <= user.id_sucursal <= 22:
            query = query.filter_by(id_sucursal=user.id_sucursal)
        elif user.id_sucursal == 100:
            if not user.department_id:
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400
            query = query.filter_by(departamento_id=user.department_id)
        elif user.id_sucursal != 1000:
            return jsonify({"mensaje": "Tipo de usuario no reconocido"}), 400

        if estado:
            query = query.filter_by(estado=estado)
        if departamento_id:
            query = query.filter_by(departamento_id=int(departamento_id))
        if criticidad:
            query = query.filter_by(criticidad=int(criticidad))
        if username:
            query = query.filter_by(username=username)
        if categoria:
            query = query.filter_by(categoria=categoria)
        if descripcion:
            query = query.filter(Ticket.descripcion.like(f"%{descripcion}%"))

        tickets = query.order_by(Ticket.fecha_creacion.desc()).all()

        wb = Workbook()
        ws = wb.active
        ws.title = "Tickets"

        headers = [
            "ID", "Descripción", "Usuario", "Estado", "Criticidad",
            "Fecha Creación", "Fecha Finalizado", "Fecha Solución",
            "Departamento ID", "Categoría", "Subcategoría", "Sub-subcategoría",
            "Problema Detectado", "Refacción", "Descripción Refacción"
        ]
        ws.append(headers)

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="0073C2")
        alt_fill = PatternFill("solid", fgColor="F2F2F2")

        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill

        for idx, ticket in enumerate(tickets, start=2):
            t = ticket.to_dict()
            ws.append([
                t.get("id"),
                t.get("descripcion"),
                t.get("username"),
                t.get("estado"),
                t.get("criticidad"),
                t.get("fecha_creacion"),
                t.get("fecha_finalizado"),
                t.get("fecha_solucion"),
                t.get("departamento_id"),
                t.get("categoria"),
                t.get("subcategoria"),
                t.get("subsubcategoria"),
                t.get("problema_detectado"),
                "Sí" if t.get("necesita_refaccion") else "No",
                t.get("descripcion_refaccion")
            ])
            if idx % 2 == 0:
                for cell in ws[idx]:
                    cell.fill = alt_fill

        for column_cells in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = max_length + 2

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

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
        return jsonify({"mensaje": f"Error interno: {str(e)}"}), 500
