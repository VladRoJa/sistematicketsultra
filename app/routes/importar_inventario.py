#C:\Users\Vladimir\Documents\Sistema tickets\app\routes\importar_inventario.py


from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from app.models.database import get_db_connection
import pandas as pd
from datetime import datetime

bp_importar = Blueprint('importar', __name__)

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

        conn = get_db_connection()
        cursor = conn.cursor()
        insertados = 0

        for fila in datos:
            descripcion = str(fila.get('descripcion', '')).strip().upper()
            categoria = str(fila.get('categoria', '')).strip().upper()
            unidad = str(fila.get('unidad', '')).strip().upper()
            sucursal = str(fila.get('sucursal', '')).strip().upper()
            fecha = str(fila.get('fecha_inventario', '')).strip()

            if not (descripcion and categoria and unidad and sucursal and fecha):
                continue

            try:
                fecha_formato = pd.to_datetime(fecha).strftime('%Y-%m-%d')
            except Exception:
                continue

            # Insertar producto si no existe
            cursor.execute("SELECT id FROM productos WHERE descripcion=%s AND categoria=%s AND unidad=%s",
                           (descripcion, categoria, unidad))
            producto = cursor.fetchone()
            if not producto:
                cursor.execute("INSERT INTO productos (descripcion, categoria, unidad) VALUES (%s, %s, %s)",
                               (descripcion, categoria, unidad))
                conn.commit()
                producto_id = cursor.lastrowid
            else:
                producto_id = producto[0]

            # Insertar sucursal si no existe
            cursor.execute("SELECT id FROM sucursales WHERE nombre=%s", (sucursal,))
            suc = cursor.fetchone()
            if not suc:
                cursor.execute("INSERT INTO sucursales (nombre) VALUES (%s)", (sucursal,))
                conn.commit()
                sucursal_id = cursor.lastrowid
            else:
                sucursal_id = suc[0]

            # Insertar inventario
            cursor.execute("""
                INSERT INTO inventario (id_producto, id_sucursal, stock_actual, gasto_mes, pedido_mes, fecha_inventario)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                producto_id,
                sucursal_id,
                float(fila.get('stock_actual') or 0),
                float(fila.get('gasto_mes') or 0),
                float(fila.get('pedido_mes') or 0),
                fecha_formato
            ))
            insertados += 1

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": f"{insertados} registros insertados"}), 200

    except Exception as e:
        return jsonify({"error": f"Error al procesar archivo: {str(e)}"}), 500
