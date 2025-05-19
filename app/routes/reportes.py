# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\reportes.py

# ------------------------------------------------------------------------------
# BLUEPRINT: REPORTES DE INVENTARIO Y MOVIMIENTOS
# ------------------------------------------------------------------------------

from flask import Blueprint, jsonify, send_file, request
from app.extensions import db
from app.models.inventario import (
    Producto, InventarioSucursal, MovimientoInventario, DetalleMovimiento
)
from io import BytesIO
import pandas as pd
from datetime import datetime, timezone
from app.utils.error_handler import manejar_error
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Ticket
from app.utils.cloudinary_upload import upload_image_to_cloudinary
from app.models.user_model import UserORM

reportes_bp = Blueprint('reportes', __name__, url_prefix='/api/reportes')

# ------------------------------------------------------------------------------
# RUTA: Exportar inventario por sucursal a Excel
# ------------------------------------------------------------------------------
@reportes_bp.route('/exportar-inventario', methods=['GET'])
def exportar_inventario():
    try:
        sucursal_id = request.args.get('sucursal_id', type=int)
        query = InventarioSucursal.query

        if sucursal_id:
            query = query.filter_by(sucursal_id=sucursal_id)

        data = query.all()
        rows = []

        for i in data:
            producto = Producto.query.get(i.producto_id)
            if not producto:
                continue

            rows.append({
                "ID Producto": producto.id,
                "Nombre": producto.nombre,
                "Unidad": producto.unidad_medida,
                "Stock": i.stock,
                "Sucursal ID": i.sucursal_id
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
        return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        return manejar_error(e, "Exportar inventario")

# ------------------------------------------------------------------------------
# RUTA: Exportar historial de movimientos a Excel
# ------------------------------------------------------------------------------
@reportes_bp.route('/exportar-movimientos', methods=['GET'])
def exportar_movimientos():
    try:
        movimientos = MovimientoInventario.query.order_by(MovimientoInventario.fecha.desc()).all()
        rows = []

        for mov in movimientos:
            detalles = DetalleMovimiento.query.filter_by(movimiento_id=mov.id).all()
            for d in detalles:
                producto = Producto.query.get(d.producto_id)
                if not producto:
                    continue

                rows.append({
                    "ID Movimiento": mov.id,
                    "Fecha": mov.fecha.strftime('%Y-%m-%d'),
                    "Hora": mov.fecha.strftime('%H:%M:%S'),
                    "Tipo": mov.tipo_movimiento,
                    "Producto": producto.nombre,
                    "Cantidad": d.cantidad,
                    "Unidad": d.unidad_medida,
                    "Sucursal ID": mov.sucursal_id,
                    "Usuario ID": mov.usuario_id,
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
        return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        return manejar_error(e, "Exportar movimientos")

# ------------------------------------------------------------------------------
# RUTA: Exportar errores dentro del sistema
# ------------------------------------------------------------------------------



from datetime import timezone

@reportes_bp.route('/reportar-error', methods=['POST'])
@jwt_required()
def reportar_error():
    try:
        descripcion = request.form.get('descripcion', '').strip()
        criticidad = request.form.get('criticidad', '1')
        modulo = request.form.get('modulo', 'Desconocido')
        usuario_id = get_jwt_identity()
        imagen = request.files.get('imagen')

        # 🔍 Log inicial
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

        # 🛠 Crear ticket
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
            fecha_creacion=datetime.now(timezone.utc)  # 🔄 En UTC correctamente
        )

        db.session.add(nuevo_ticket)
        db.session.commit()

        print("✅ Ticket de bug creado correctamente (ID:", nuevo_ticket.id, ")")
        return jsonify({"message": "Reporte enviado correctamente"}), 201

    except Exception as e:
        print("❌ Excepción atrapada en reportar_error:", str(e))
        return manejar_error(e, "Reportar error con imagen")
