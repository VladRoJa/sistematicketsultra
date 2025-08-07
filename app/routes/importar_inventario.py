# app\routes\importar_inventario.py

# app/routes/importar_inventario.py

from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
from extensions import db
from models.inventario import InventarioGeneral, InventarioSucursal
from models.sucursal_model import Sucursal
from utils.string_utils import normalizar_campo
import pandas as pd
import io
from flask_jwt_extended import jwt_required


bp_importar = Blueprint('importar', __name__)

# --- Carga masiva de catálogo (productos) ---
@bp_importar.route('/catalogo', methods=['POST'])
@jwt_required()
def importar_catalogo():
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
        creados, actualizados, errores = 0, 0, []
        for idx, fila in df.iterrows():
            nombre = normalizar_campo(str(fila.get('nombre', '')))
            marca = normalizar_campo(str(fila.get('marca', '')))
            if not nombre or not marca:
                errores.append(f'Fila {idx+2}: Falta nombre o marca')
                continue
            existe = InventarioGeneral.query.filter_by(nombre=nombre, marca=marca).first()
            if existe:
                actualizados += 1
                continue
            inventario = InventarioGeneral(
                tipo=normalizar_campo(str(fila.get('tipo', 'producto'))),
                nombre=nombre,
                marca=marca,
                descripcion=normalizar_campo(str(fila.get('descripcion', ''))),
                categoria=normalizar_campo(str(fila.get('categoria', ''))),
                unidad=normalizar_campo(str(fila.get('unidad', ''))),
                proveedor=normalizar_campo(str(fila.get('proveedor', '')))
            )
            db.session.add(inventario)
            creados += 1
        db.session.commit()
        msg = f'🟢 {creados} productos creados. '
        if actualizados: msg += f'⚠️ {actualizados} ya existían. '
        if errores: msg += f'❌ Errores: {"; ".join(errores)}'
        return jsonify({'mensaje': msg})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al importar catálogo: {str(e)}"}), 500


# --- Carga masiva de existencias (stock) ---
@bp_importar.route('/existencias', methods=['POST'])
@jwt_required()
def importar_existencias():
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
        actualizados, errores = 0, []
        for idx, fila in df.iterrows():
            nombre = normalizar_campo(str(fila.get('nombre', '')))
            marca = normalizar_campo(str(fila.get('marca', '')))
            sucursal_nombre = normalizar_campo(str(fila.get('sucursal', '')))
            stock = int(float(fila.get('stock', 0) or 0))
            if not (nombre and marca and sucursal_nombre):
                errores.append(f'Fila {idx+2}: Falta nombre, marca o sucursal')
                continue
            producto = InventarioGeneral.query.filter_by(nombre=nombre, marca=marca).first()
            if not producto:
                errores.append(f'Fila {idx+2}: Producto "{nombre} {marca}" no encontrado')
                continue
            sucursal = Sucursal.query.filter_by(sucursal=sucursal_nombre).first()
            if not sucursal:
                errores.append(f'Fila {idx+2}: Sucursal "{sucursal_nombre}" no encontrada')
                continue
            inv_suc = InventarioSucursal.query.filter_by(inventario_id=producto.id, sucursal_id=sucursal.sucursal_id).first()
            if not inv_suc:
                inv_suc = InventarioSucursal(inventario_id=producto.id, sucursal_id=sucursal.sucursal_id, stock=stock)
                db.session.add(inv_suc)
            else:
                inv_suc.stock = stock
            actualizados += 1
        db.session.commit()
        msg = f'🟢 {actualizados} existencias actualizadas. '
        if errores: msg += f'❌ Errores: {"; ".join(errores)}'
        return jsonify({'mensaje': msg})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al importar existencias: {str(e)}"}), 500

@bp_importar.route('/layout/<tipo>', methods=['GET'])
@jwt_required()
def descargar_layout(tipo):
    if tipo == 'catalogo':
        columns = ['nombre', 'marca', 'tipo', 'descripcion', 'categoria', 'unidad', 'proveedor']
    elif tipo == 'existencias':
        columns = ['nombre', 'marca', 'sucursal', 'stock']
    else:
        return jsonify({'error': 'Tipo de layout no válido'}), 400
    df = pd.DataFrame(columns=columns)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f'layout_{tipo}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

