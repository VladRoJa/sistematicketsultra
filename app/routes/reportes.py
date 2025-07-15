from flask import Blueprint, jsonify, send_file, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.inventario import (
    InventarioGeneral, InventarioSucursal, MovimientoInventario, DetalleMovimiento
)
from app.models.user_model import UserORM
from app.models.sucursal_model import Sucursal
from app.models import Ticket
from app.utils.error_handler import manejar_error
from app.utils.cloudinary_upload import upload_image_to_cloudinary
from io import BytesIO
from datetime import datetime, timezone
import pandas as pd

reportes_bp = Blueprint('reportes', __name__, url_prefix='/api/reportes')

# ═══════════════════════════════════════════════════════════════════════
# EXPORTAR INVENTARIO GENERAL (con filtros avanzados)
# ═══════════════════════════════════════════════════════════════════════

@reportes_bp.route('/exportar-inventario', methods=['GET'])
@jwt_required()
def exportar_inventario():
    try:
        # Filtros por query params
        categoria = request.args.get('categoria')
        tipo = request.args.get('tipo')
        proveedor = request.args.get('proveedor')

        query = InventarioGeneral.query

        if categoria:
            query = query.filter(InventarioGeneral.categoria.ilike(f"%{categoria}%"))
        if tipo:
            query = query.filter(InventarioGeneral.tipo.ilike(f"%{tipo}%"))
        if proveedor:
            query = query.filter(InventarioGeneral.proveedor.ilike(f"%{proveedor}%"))

        data = query.all()
        rows = []
        for i in data:
            rows.append({
                "ID": i.id,
                "Tipo": i.tipo,
                "Nombre": i.nombre,
                "Descripción": i.descripcion,
                "Marca": i.marca,
                "Proveedor": i.proveedor,
                "Categoría": i.categoria,
                "Unidad": i.unidad,
                "Código Interno": i.codigo_interno,
                "No. de Equipo": i.no_equipo,
                "Gasto Semanal": i.gasto_sem,
                "Gasto Mensual": i.gasto_mes,
                "Pedido Mensual": i.pedido_mes,
                "Semana Pedido": i.semana_pedido,
                "Fecha Inventario": str(i.fecha_inventario) if i.fecha_inventario else None,
            })

        df = pd.DataFrame(rows)
        if df.empty:
            return jsonify({"error": "No hay datos de inventario para exportar"}), 400

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Inventario', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Inventario']

            header_format = workbook.add_format({'bold': True, 'bg_color': '#B4C6E7'})
            for col_num, value in enumerate(df.columns):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 20)
            worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)

        output.seek(0)
        filename = f'Inventario_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return send_file(output, as_attachment=True, download_name=filename,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return manejar_error(e, "Exportar inventario")


# ═══════════════════════════════════════════════════════════════════════
# EXPORTAR MOVIMIENTOS DE INVENTARIO (con filtros avanzados)
# ═══════════════════════════════════════════════════════════════════════

@reportes_bp.route('/exportar-movimientos', methods=['GET'])
@jwt_required()
def exportar_movimientos():
    try:
        # Filtros avanzados
        fecha_desde = request.args.get('fecha_desde')
        fecha_hasta = request.args.get('fecha_hasta')
        sucursal_id = request.args.get('sucursal_id', type=int)
        tipo_movimiento = request.args.get('tipo')
        usuario_id = request.args.get('usuario_id', type=int)

        query = MovimientoInventario.query

        if fecha_desde:
            query = query.filter(MovimientoInventario.fecha >= fecha_desde)
        if fecha_hasta:
            query = query.filter(MovimientoInventario.fecha <= fecha_hasta)
        if sucursal_id:
            query = query.filter_by(sucursal_id=sucursal_id)
        if tipo_movimiento:
            query = query.filter_by(tipo_movimiento=tipo_movimiento)
        if usuario_id:
            query = query.filter_by(usuario_id=usuario_id)

        movimientos = query.order_by(MovimientoInventario.fecha.desc()).all()
        rows = []
        for mov in movimientos:
            detalles = DetalleMovimiento.query.filter_by(movimiento_id=mov.id).all()
            usuario = UserORM.query.get(mov.usuario_id)
            sucursal = Sucursal.query.get(mov.sucursal_id)
            for d in detalles:
                inventario = InventarioGeneral.query.get(d.inventario_id)
                if not inventario:
                    continue
                rows.append({
                    "ID Movimiento": mov.id,
                    "Fecha": mov.fecha.strftime('%Y-%m-%d'),
                    "Hora": mov.fecha.strftime('%H:%M:%S'),
                    "Tipo": mov.tipo_movimiento,
                    "Inventario": inventario.nombre,
                    "Inventario ID": inventario.id,
                    "Cantidad": d.cantidad,
                    "Unidad": d.unidad_medida,
                    "Sucursal ID": mov.sucursal_id,
                    "Sucursal": sucursal.sucursal if sucursal else "",
                    "Usuario ID": mov.usuario_id,
                    "Usuario": usuario.username if usuario else "",
                    "Observaciones": mov.observaciones
                })

        df = pd.DataFrame(rows)
        if df.empty:
            return jsonify({"error": "No hay movimientos registrados para exportar"}), 400

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Movimientos', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Movimientos']

            header_format = workbook.add_format({'bold': True, 'bg_color': '#B4C6E7'})
            for col_num, value in enumerate(df.columns):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 20)
            worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)

        output.seek(0)
        filename = f'Movimientos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return send_file(output, as_attachment=True, download_name=filename,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return manejar_error(e, "Exportar movimientos")


# ═══════════════════════════════════════════════════════════════════════
# REPORTE RESUMEN GLOBAL DE EXISTENCIAS POR SUCURSAL
# ═══════════════════════════════════════════════════════════════════════

@reportes_bp.route('/inventario-resumen-sucursales', methods=['GET'])
@jwt_required()
def inventario_resumen_sucursales():
    try:
        sucursales = Sucursal.query.all()
        data = []
        for suc in sucursales:
            total = db.session.query(db.func.sum(InventarioSucursal.stock)).filter_by(sucursal_id=suc.sucursal_id).scalar() or 0
            data.append({
                "Sucursal ID": suc.sucursal_id,
                "Sucursal": suc.sucursal,
                "Stock Total": total
            })
        return jsonify(data), 200
    except Exception as e:
        return manejar_error(e, "Resumen de inventario por sucursal")


# ═══════════════════════════════════════════════════════════════════════
# REPORTE RESUMEN GLOBAL DE EXISTENCIAS POR CATEGORÍA
# ═══════════════════════════════════════════════════════════════════════

@reportes_bp.route('/inventario-resumen-categorias', methods=['GET'])
@jwt_required()
def inventario_resumen_categorias():
    try:
        rows = db.session.query(
            InventarioGeneral.categoria,
            db.func.sum(InventarioSucursal.stock)
        ).join(
            InventarioSucursal, InventarioSucursal.inventario_id == InventarioGeneral.id
        ).group_by(InventarioGeneral.categoria).all()
        data = [{
            "Categoría": cat or "Sin categoría",
            "Stock Total": stock or 0
        } for cat, stock in rows]
        return jsonify(data), 200
    except Exception as e:
        return manejar_error(e, "Resumen de inventario por categoría")


# ═══════════════════════════════════════════════════════════════════════
# REPORTE RÁPIDO DE INVENTARIO BAJO STOCK
# ═══════════════════════════════════════════════════════════════════════

@reportes_bp.route('/inventario-bajo-stock', methods=['GET'])
@jwt_required()
def inventario_bajo_stock():
    try:
        umbral = request.args.get('umbral', default=10, type=int)
        query = InventarioSucursal.query.filter(InventarioSucursal.stock <= umbral)
        data = [{
            "ID": s.inventario_id,
            "Nombre": s.inventario.nombre if s.inventario else "Desconocido",
            "Categoría": s.inventario.categoria if s.inventario else "Sin categoría",
            "Sucursal ID": s.sucursal_id,
            "Stock Actual": s.stock
        } for s in query.all()]
        return jsonify(data), 200
    except Exception as e:
        return manejar_error(e, "Inventario bajo stock")


# ═══════════════════════════════════════════════════════════════════════
# REPORTE DE ERRORES (Tickets de bug)
# ═══════════════════════════════════════════════════════════════════════

@reportes_bp.route('/reportar-error', methods=['POST'])
@jwt_required()
def reportar_error():
    try:
        descripcion = request.form.get('descripcion', '').strip()
        criticidad = request.form.get('criticidad', '1')
        modulo = request.form.get('modulo', 'Desconocido')
        usuario_id = get_jwt_identity()
        imagen = request.files.get('imagen')

        print("📥 Reporte de bug recibido")
        print("📝 Descripción:", descripcion)
        print("⚠️ Criticidad:", criticidad)
        print("📍 Módulo:", modulo)
        print("🧾 Imagen recibida:", "Sí" if imagen else "No")
        print("🔐 Usuario ID:", usuario_id)

        user = UserORM.get_by_id(usuario_id)
        if not user:
            print("❌ Usuario no encontrado en la base de datos")
            return jsonify({"error": "Usuario no encontrado"}), 404

        url_imagen = None
        if imagen:
            try:
                url_imagen = upload_image_to_cloudinary(imagen)
                print("📸 Imagen subida correctamente:", url_imagen)
            except Exception as e:
                print("❌ Error al subir imagen:", str(e))

        if not descripcion:
            print("⚠️ Descripción vacía, cancelando reporte")
            return jsonify({"error": "Descripción es obligatoria"}), 400

        nuevo_ticket = Ticket(
            descripcion=f"[BUG] Módulo: {modulo} | {descripcion or 'Sin descripción'}",
            username=user.username,
            sucursal_id=user.sucursal_id,
            estado='abierto',
            criticidad=int(criticidad) if criticidad.isdigit() else 1,
            departamento_id=7,
            categoria='Errores',
            subcategoria=modulo,
            subsubcategoria=None,
            aparato_id=None,
            problema_detectado=None,
            necesita_refaccion=False,
            descripcion_refaccion=None,
            url_evidencia=url_imagen,
            fecha_creacion=datetime.now(timezone.utc)
        )

        db.session.add(nuevo_ticket)
        db.session.commit()

        print("✅ Ticket de bug creado correctamente (ID:", nuevo_ticket.id, ")")
        return jsonify({"message": "Reporte enviado correctamente"}), 201

    except Exception as e:
        print("❌ Excepción atrapada en reportar_error:", str(e))
        return manejar_error(e, "Reportar error con imagen")
