# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\importar_inventario.py

# ------------------------------------------------------------------------------
# BLUEPRINT: IMPORTAR INVENTARIO DESDE EXCEL O CSV
# ------------------------------------------------------------------------------

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import pandas as pd
from app.extensions import db
from app.models.inventario import Producto, InventarioSucursal
from app.models.sucursal_model import Sucursal
from datetime import datetime

bp_importar = Blueprint('importar', __name__)

# ------------------------------------------------------------------------------
# RUTA: Importar archivo de inventario (Excel o CSV)
# ------------------------------------------------------------------------------
@bp_importar.route('/api/importar-archivo', methods=['POST'])
def importar_archivo():
    if 'archivo' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400

    archivo = request.files['archivo']
    filename = secure_filename(archivo.filename)

    try:
        if filename.endswith('.xlsx'):
            df = pd.read_excel(archivo)
        elif filename.endswith('.csv'):
            df = pd.read_csv(archivo)
        else:
            return jsonify({"error": "Formato de archivo no permitido"}), 400

        df = df.fillna('')
        datos = df.to_dict(orient='records')

        insertados = 0

        for fila in datos:
            descripcion = str(fila.get('descripcion', '')).strip().upper()
            categoria = str(fila.get('categoria', '')).strip().upper()
            unidad = str(fila.get('unidad', '')).strip().upper()
            sucursal_nombre = str(fila.get('sucursal', '')).strip().upper()
            fecha = str(fila.get('fecha_inventario', '')).strip()

            if not (descripcion and categoria and unidad and sucursal_nombre and fecha):
                continue

            try:
                fecha_formateada = pd.to_datetime(fecha).strftime('%Y-%m-%d')
            except Exception:
                continue

            # Buscar o crear producto
            producto = Producto.query.filter_by(
                nombre=descripcion,
                categoria=categoria,
                unidad_medida=unidad
            ).first()

            if not producto:
                producto = Producto(
                    nombre=descripcion,
                    categoria=categoria,
                    unidad_medida=unidad
                )
                db.session.add(producto)
                db.session.flush()  # 🔥 Obtener ID sin hacer commit inmediato

            # Buscar o crear sucursal
            sucursal = Sucursal.query.filter_by(sucursal=sucursal_nombre).first()
            if not sucursal:
                sucursal = Sucursal(
                    serie='N/A',
                    sucursal=sucursal_nombre,
                    estado='N/A',
                    municipio='N/A',
                    direccion='N/A'
                )
                db.session.add(sucursal)
                db.session.flush()

            # Insertar inventario
            inventario = InventarioSucursal(
                producto_id=producto.id,
                sucursal_id=sucursal.id_sucursal,
                stock=float(fila.get('stock_actual') or 0)
            )
            db.session.add(inventario)
            insertados += 1

        db.session.commit()

        return jsonify({"mensaje": f"{insertados} registros insertados"}), 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error al procesar archivo: {e}")
        return jsonify({"error": f"Error al procesar archivo: {str(e)}"}), 500
    
