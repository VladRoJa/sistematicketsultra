# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\ticket_routes.py

from flask import Blueprint, jsonify, request, send_file
from flask_cors import CORS
from flask_jwt_extended import get_jwt_identity, jwt_required
from datetime import datetime, timezone, time
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
import pytz
from sqlalchemy import or_
from config import Config
from sqlalchemy import or_
from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.extensions import db
from app.utils.error_handler import manejar_error
from dateutil import parser
from sqlalchemy.orm.attributes import flag_modified
from app.utils.datetime_utils import format_datetime 



# ─────────────────────────────────────────────────────────────
# BLUEPRINT: TICKETS
# ─────────────────────────────────────────────────────────────
ticket_bp = Blueprint('tickets', __name__, url_prefix='/api/tickets')



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
            sucursal_id=user.sucursal_id,
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
        return manejar_error(e)


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

        if user.sucursal_id is None:
            return jsonify({"mensaje": "El usuario no tiene sucursal asignada"}), 400

        limit = request.args.get('limit', default=15, type=int)
        offset = request.args.get('offset', default=0, type=int)

        query = Ticket.query

        if isinstance(user.sucursal_id, int) and 1 <= user.sucursal_id <= 22:
            query = query.filter_by(sucursal_id=user.sucursal_id)
        elif user.sucursal_id == 100:
            if user.department_id is None:
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400
            query = query.filter_by(departamento_id=user.department_id)
        elif user.sucursal_id != 1000:
            return jsonify({"mensaje": "Tipo de usuario no reconocido"}), 400

        total_tickets = query.count()
        tickets = query.order_by(Ticket.id.desc()).limit(limit).offset(offset).all()

        return jsonify({
            "mensaje": "Tickets cargados correctamente",
            "tickets": [t.to_dict() for t in tickets],
            "total_tickets": total_tickets
        }), 200

    except Exception as e:
        return manejar_error(e)


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

        if 1 <= user.sucursal_id <= 22:
            query = query.filter_by(sucursal_id=user.sucursal_id)
        elif user.sucursal_id == 100:
            if not user.department_id:
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400
            query = query.filter_by(departamento_id=user.department_id)
        elif user.sucursal_id != 1000:
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

        tickets = query.order_by(Ticket.id.desc()).all()


        return jsonify({
            "mensaje": "Tickets filtrados",
            "tickets": [t.to_dict() for t in tickets],
            "total_tickets": total_tickets
        }), 200

    except Exception as e:
        return manejar_error(e)


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
        historial_nuevo = data.get("historial_fechas", [])


        if not estado:
            return jsonify({"mensaje": "Estado es requerido"}), 400

        ticket.estado = estado
        ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if estado == "finalizado":
            print(f"🕒 Fecha finalizado: {ahora}")
            ticket.fecha_finalizado = ahora
        elif estado == "en progreso":
            print(f"🕒 Fecha en progreso: {ahora}")
            ticket.fecha_en_progreso = ahora

        if fecha_solucion:
            fecha_parsed = parser.isoparse(fecha_solucion)
            ticket.fecha_solucion = fecha_parsed.astimezone(timezone.utc)

        # 🌐 Normalizar historial nuevo
        tz_mx = pytz.timezone("America/Tijuana")
        historial_final = ticket.historial_fechas or []

        motivo_cambio = data.get("motivo_cambio", "").strip()

        for entrada in historial_nuevo:
            nueva = entrada.copy()
            for campo in ['fecha', 'fechaCambio']:
                valor = nueva.get(campo)
                if valor:
                    try:
                        if '/' in valor and len(valor) == 8:
                            fecha_local = datetime.strptime(valor, "%d/%m/%y")
                            fecha_local = tz_mx.localize(datetime.combine(fecha_local.date(), time(hour=7)))
                            nueva[campo] = fecha_local.astimezone(timezone.utc).isoformat()
                        else:
                            nueva[campo] = parser.isoparse(valor).astimezone(timezone.utc).isoformat()
                    except Exception as e:
                        print(f"❌ Error parseando {campo} en ticket #{ticket.id}: {e}")
                        continue

            # ✅ Agregar motivo si no viene desde el frontend
            if motivo_cambio and 'motivo' not in nueva:
                nueva['motivo'] = motivo_cambio

            existe_misma_fecha = any(
                parser.isoparse(e.get("fecha")).replace(tzinfo=None) == parser.isoparse(nueva.get("fecha")).replace(tzinfo=None)
                for e in historial_final if e.get("fecha")
            )

            if not existe_misma_fecha:
                historial_final.append(nueva)

        
        
        historial_final.sort(key=lambda x: parser.isoparse(x['fechaCambio']), reverse=True)
        # ✅ Asignar y marcar como modificado una vez al final
        ticket.historial_fechas = historial_final
        flag_modified(ticket, 'historial_fechas')
        print(f"✅ Historial final para ticket #{ticket.id}: {historial_final}")

        db.session.commit()
        return jsonify({"mensaje": f"Ticket {id} actualizado correctamente"}), 200

    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "update_ticket_status")

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
        return manejar_error(e)


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

        # 🔄 MULTI-VALORES
        estados = request.args.getlist('estado')
        departamentos = request.args.getlist('departamento_id')
        criticidades = request.args.getlist('criticidad')
        usernames = request.args.getlist('username')
        categorias = request.args.getlist('categoria')
        subcategorias = request.args.getlist('subcategoria')
        subsubcategorias = request.args.getlist('subsubcategoria')
        descripciones = request.args.getlist('descripcion')

        # 🔎 Fechas
        fecha_desde = request.args.get('fecha_desde')
        fecha_hasta = request.args.get('fecha_hasta')
        fecha_fin_desde = request.args.get('fecha_fin_desde')
        fecha_fin_hasta = request.args.get('fecha_fin_hasta')
        fecha_prog_desde = request.args.get('fecha_prog_desde')
        fecha_prog_hasta = request.args.get('fecha_prog_hasta')

        query = Ticket.query

        # 🔐 Filtro por rol
        if 1 <= user.sucursal_id <= 22:
            query = query.filter_by(sucursal_id=user.sucursal_id)
        elif user.sucursal_id == 100:
            if not user.department_id:
                return jsonify({"mensaje": "Supervisor sin departamento asignado"}), 400
            query = query.filter_by(departamento_id=user.department_id)
        elif user.sucursal_id != 1000:
            return jsonify({"mensaje": "Tipo de usuario no reconocido"}), 400

        # 🧠 Aplicar MULTI-FILTROS
        if estados:
            query = query.filter(Ticket.estado.in_(estados))
        if departamentos:
            query = query.filter(Ticket.departamento_id.in_([int(d) for d in departamentos]))
        if criticidades:
            query = query.filter(Ticket.criticidad.in_([int(c) for c in criticidades]))
        if usernames:
            query = query.filter(Ticket.username.in_(usernames))

        # Filtros con posible "—"
        def filtrar_con_null(campo, valores):
            condiciones = []
            for v in valores:
                if v == "—":
                    condiciones.append(campo.is_(None))
                else:
                    condiciones.append(campo == v)
            return or_(*condiciones)

        if categorias:
            query = query.filter(filtrar_con_null(Ticket.categoria, categorias))
        if subcategorias:
            query = query.filter(filtrar_con_null(Ticket.subcategoria, subcategorias))
        if subsubcategorias:
            query = query.filter(filtrar_con_null(Ticket.subsubcategoria, subsubcategorias))
        if descripciones:
            query = query.filter(filtrar_con_null(Ticket.descripcion, descripciones))

        # 📅 Filtros por fecha
        if fecha_desde:
            query = query.filter(Ticket.fecha_creacion >= datetime.strptime(fecha_desde, '%Y-%m-%d'))
        if fecha_hasta:
            query = query.filter(Ticket.fecha_creacion <= datetime.strptime(fecha_hasta, '%Y-%m-%d'))
        if fecha_fin_desde:
            query = query.filter(Ticket.fecha_finalizado >= datetime.strptime(fecha_fin_desde, '%Y-%m-%d'))
        if fecha_fin_hasta:
            query = query.filter(Ticket.fecha_finalizado <= datetime.strptime(fecha_fin_hasta, '%Y-%m-%d'))
        if fecha_prog_desde:
            query = query.filter(Ticket.fecha_en_progreso >= datetime.strptime(fecha_prog_desde, '%Y-%m-%d'))
        if fecha_prog_hasta:
            query = query.filter(Ticket.fecha_en_progreso <= datetime.strptime(fecha_prog_hasta, '%Y-%m-%d'))

        # 📋 Obtener tickets
        tickets = query.order_by(Ticket.fecha_creacion.desc()).all()

        # 🧾 Crear Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Tickets"

        headers = [
            "ID", "Descripción", "Usuario", "Estado", "Criticidad",
            "Fecha Creación", "Fecha En Progreso", "Fecha Finalizado", "Fecha Solución",
            "Departamento", "Categoría", "Subcategoría", "Sub-subcategoría",
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

            # ✅ Formatear fecha solución como día/mes/año
            fecha_solucion_corta = ""
            if ticket.fecha_solucion:
                fecha_solucion_corta = ticket.fecha_solucion.astimezone(pytz.timezone("America/Tijuana")).strftime('%d/%m/%Y')

            ws.append([
                t.get("id"),
                t.get("descripcion"),
                t.get("username"),
                t.get("estado"),
                t.get("criticidad"),
                t.get("fecha_creacion"),
                t.get("fecha_en_progreso"),
                t.get("fecha_finalizado"),
                fecha_solucion_corta,
                ticket.departamento.nombre if ticket.departamento else "—",
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
        return manejar_error(e)


# ─────────────────────────────────────────────────────────────
# RUTA: migrar tickets a ISO local
# ─────────────────────────────────────────────────────────────


from flask_jwt_extended import jwt_required

@ticket_bp.route('/migrar-historial-local', methods=['POST'])
@jwt_required()
def migrar_historial_local():
    from datetime import datetime, timezone, time
    import pytz

    tz_mx = pytz.timezone("America/Tijuana")
    tickets = Ticket.query.all()
    total_actualizados = 0

    for ticket in tickets:
        historial = ticket.historial_fechas
        if not historial:
            continue

        actualizado = False
        nuevo_historial = []

        for entrada in historial:
            nueva_entrada = entrada.copy()
            for campo in ['fecha', 'fechaCambio']:
                valor = entrada.get(campo)
                if valor and isinstance(valor, str) and '/' in valor and len(valor) == 8:
                    try:
                        fecha_local = datetime.strptime(valor, "%d/%m/%y")
                        fecha_local = tz_mx.localize(datetime.combine(fecha_local.date(), time(hour=7)))
                        fecha_utc = fecha_local.astimezone(timezone.utc)
                        nueva_entrada[campo] = fecha_utc.isoformat()
                        actualizado = True
                    except Exception as e:
                        print(f"❌ Error en ticket #{ticket.id}, campo {campo}: {e}")
            nuevo_historial.append(nueva_entrada)

        if actualizado:
            ticket.historial_fechas = nuevo_historial
            total_actualizados += 1

    if total_actualizados > 0:
        db.session.commit()
        return jsonify({"mensaje": f"✅ Historial actualizado en {total_actualizados} tickets."}), 200
    else:
        return jsonify({"mensaje": "⚠️ No se encontraron entradas para actualizar."}), 200


# ─────────────────────────────────────────────────────────────
# RUTA: migrar tickets a ISO railway
# ─────────────────────────────────────────────────────────────

@ticket_bp.route('/migrar-historial-railway', methods=['POST'])
@jwt_required()
def migrar_historial_railway():
    from datetime import datetime, timezone, time
    import pytz
    from app.models.ticket_model import Ticket
    from app.extensions import db

    tz_mx = pytz.timezone("America/Tijuana")
    tickets = Ticket.query.all()
    total_actualizados = 0

    for ticket in tickets:
        historial = ticket.historial_fechas
        if not historial:
            continue

        actualizado = False
        nuevo_historial = []

        for entrada in historial:
            nueva_entrada = entrada.copy()
            for campo in ['fecha', 'fechaCambio']:
                valor = entrada.get(campo)
                if valor and isinstance(valor, str) and '/' in valor and len(valor) == 8:
                    try:
                        fecha_local = datetime.strptime(valor, "%d/%m/%y")
                        fecha_local = tz_mx.localize(datetime.combine(fecha_local.date(), time(hour=7)))
                        fecha_utc = fecha_local.astimezone(timezone.utc)
                        nueva_entrada[campo] = fecha_utc.isoformat()
                        actualizado = True
                    except Exception as e:
                        print(f"❌ Error en ticket #{ticket.id}, campo {campo}: {e}")
            nuevo_historial.append(nueva_entrada)

        if actualizado:
            ticket.historial_fechas = nuevo_historial
            total_actualizados += 1

    if total_actualizados > 0:
        db.session.commit()
        return jsonify({"mensaje": f"✅ Historial actualizado en {total_actualizados} tickets (Railway)."}), 200
    else:
        return jsonify({"mensaje": "⚠️ No se encontraron entradas para actualizar (Railway)."}), 200

# ─────────────────────────────────────────────────────────────
# RUTA: eliminar todos tickets
# ─────────────────────────────────────────────────────────────

# Ruta temporal y protegida para borrar todos los tickets
from flask_jwt_extended import jwt_required
from app.models.ticket_model import Ticket
from app.extensions import db
from flask import Blueprint, jsonify

@ticket_bp.route('/eliminar-todos', methods=['DELETE'])
@jwt_required()
def eliminar_todos_los_tickets():
    try:
        cantidad = Ticket.query.delete()
        db.session.commit()
        return jsonify({"mensaje": f"🧨 Se eliminaron {cantidad} tickets."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
