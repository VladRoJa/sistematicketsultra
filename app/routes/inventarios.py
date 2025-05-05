# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\inventarios.py

from flask import Blueprint, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.inventario import Producto, MovimientoInventario, DetalleMovimiento, InventarioSucursal
from app.models.user_model import UserORM
from app.models.sucursal_model import Sucursal
from datetime import datetime
from config import Config

inventario_bp = Blueprint('inventario', __name__, url_prefix='/api/inventario')
CORS(inventario_bp, resources={r"/*": {"origins": Config.CORS_ORIGINS}}, supports_credentials=True)

# ----------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------

def error_response(message, status_code=400):
    return jsonify({'error': message}), status_code

def success_response(message, extra=None):
    res = {'message': message}
    if extra:
        res.update(extra)
    return jsonify(res), 200

# ----------------------------------------------------------------------
# RUTAS
# ----------------------------------------------------------------------

@inventario_bp.route('/ping', methods=['GET'])
def ping():
    return success_response('Pong!')

# Crear un nuevo producto
@inventario_bp.route('/productos', methods=['POST'])
@jwt_required()
def crear_producto():
    try:
        data = request.get_json()
        if not data.get('nombre') or not data.get('categoria'):
            return error_response('Nombre y categoría son obligatorios')

        if Producto.query.filter_by(nombre=data['nombre']).first():
            return error_response('Ya existe un producto con ese nombre')

        nuevo_producto = Producto(
            nombre=data['nombre'],
            descripcion=data.get('descripcion'),
            unidad_medida=data.get('unidad_medida'),
            categoria=data['categoria'],
            subcategoria=data.get('subcategoria')
        )

        db.session.add(nuevo_producto)
        db.session.commit()
        return success_response('Producto creado correctamente', {'producto_id': nuevo_producto.id})

    except Exception as e:
        db.session.rollback()
        return error_response(f"Error interno: {str(e)}", 500)

# Obtener todos los productos
@inventario_bp.route('/productos', methods=['GET'])
@jwt_required()
def obtener_productos():
    productos = Producto.query.all()
    data = [{
        'id': p.id,
        'nombre': p.nombre,
        'unidad_medida': p.unidad_medida,
        'categoria': p.categoria
    } for p in productos]
    return jsonify(data), 200

# Registrar entrada/salida
@inventario_bp.route('/movimientos', methods=['POST'])
@jwt_required()
def registrar_movimiento():
    try:
        data = request.get_json()
        tipo = data.get('tipo_movimiento')
        sucursal_id = data.get('sucursal_id')
        usuario_id = data.get('usuario_id')
        productos = data.get('productos', [])
        observaciones = data.get('observaciones', '')

        if tipo not in ['entrada', 'salida'] or not productos:
            return error_response('Datos inválidos')

        nuevo_movimiento = MovimientoInventario(
            tipo_movimiento=tipo,
            sucursal_id=sucursal_id,
            usuario_id=usuario_id,
            observaciones=observaciones
        )
        db.session.add(nuevo_movimiento)
        db.session.flush()  # Obtener ID antes de commit

        for p in productos:
            producto_id = p['producto_id']
            cantidad = int(p['cantidad'])
            unidad = p.get('unidad_medida')

            detalle = DetalleMovimiento(
                movimiento_id=nuevo_movimiento.id,
                producto_id=producto_id,
                cantidad=cantidad,
                unidad_medida=unidad
            )
            db.session.add(detalle)

            inventario = InventarioSucursal.query.filter_by(
                producto_id=producto_id,
                sucursal_id=sucursal_id
            ).first()

            if not inventario:
                inventario = InventarioSucursal(
                    producto_id=producto_id,
                    sucursal_id=sucursal_id,
                    stock=0
                )
                db.session.add(inventario)

            if tipo == 'entrada':
                inventario.stock += cantidad
            else:  # salida
                if inventario.stock < cantidad:
                    db.session.rollback()
                    return error_response(f'Stock insuficiente para el producto {producto_id}')
                inventario.stock -= cantidad

        db.session.commit()
        return success_response('Movimiento registrado correctamente', {'movimiento_id': nuevo_movimiento.id})

    except Exception as e:
        db.session.rollback()
        return error_response(f"Error interno: {str(e)}", 500)

# Consultar inventario por sucursal
@inventario_bp.route('/sucursal/<int:sucursal_id>', methods=['GET'])
@jwt_required()
def obtener_inventario_por_sucursal(sucursal_id):
    inventario = InventarioSucursal.query.filter_by(sucursal_id=sucursal_id).all()
    resultado = []

    for item in inventario:
        producto = Producto.query.get(item.producto_id)
        ultimo_mov = MovimientoInventario.query.join(DetalleMovimiento).filter(
            DetalleMovimiento.producto_id == item.producto_id,
            MovimientoInventario.sucursal_id == sucursal_id
        ).order_by(MovimientoInventario.fecha.desc()).first()

        resultado.append({
            'producto_id': producto.id,
            'nombre': producto.nombre,
            'stock': item.stock,
            'unidad_medida': producto.unidad_medida,
            'ultimo_movimiento': ultimo_mov.fecha.strftime('%d/%m/%y %H:%M') if ultimo_mov else 'N/A'
        })

    return jsonify(resultado), 200

# Ver historial de movimientos
@inventario_bp.route('/movimientos', methods=['GET'])
@jwt_required()
def historial_movimientos():
    sucursal_id = request.args.get('sucursal_id', type=int)
    tipo = request.args.get('tipo_movimiento')

    query = MovimientoInventario.query
    if sucursal_id:
        query = query.filter_by(sucursal_id=sucursal_id)
    if tipo:
        query = query.filter_by(tipo_movimiento=tipo)

    movimientos = query.order_by(MovimientoInventario.fecha.desc()).all()
    resultado = []

    for m in movimientos:
        detalles = DetalleMovimiento.query.filter_by(movimiento_id=m.id).all()
        productos = [{
            'producto_id': d.producto_id,
            'cantidad': d.cantidad,
            'unidad_medida': d.unidad_medida
        } for d in detalles]

        sucursal = Sucursal.query.get(m.sucursal_id)
        usuario = UserORM.query.get(m.usuario_id)

        resultado.append({
            'movimiento_id': m.id,
            'tipo': m.tipo_movimiento,
            'fecha': m.fecha.strftime('%d/%m/%y %H:%M'),
            'usuario_nombre': usuario.username if usuario else "Desconocido",
            'sucursal_nombre': sucursal.sucursal if sucursal else "Desconocida",
            'observaciones': m.observaciones,
            'productos': productos
        })

    return jsonify(resultado), 200

# Editar producto
@inventario_bp.route('/productos/<int:producto_id>', methods=['PUT'])
@jwt_required()
def editar_producto(producto_id):
    producto = Producto.query.get(producto_id)
    if not producto:
        return error_response('Producto no encontrado', 404)

    data = request.get_json()
    nuevo_nombre = data.get('nombre')

    if not nuevo_nombre or not data.get('categoria'):
        return error_response('Nombre y categoría son obligatorios')

    if Producto.query.filter(Producto.nombre == nuevo_nombre, Producto.id != producto_id).first():
        return error_response('Ya existe otro producto con ese nombre')

    producto.nombre = nuevo_nombre
    producto.descripcion = data.get('descripcion', producto.descripcion)
    producto.unidad_medida = data.get('unidad_medida', producto.unidad_medida)
    producto.categoria = data.get('categoria', producto.categoria)
    producto.subcategoria = data.get('subcategoria', producto.subcategoria)

    db.session.commit()
    return success_response('Producto actualizado correctamente')

# Eliminar producto
@inventario_bp.route('/productos/<int:producto_id>', methods=['DELETE'])
@jwt_required()
def eliminar_producto(producto_id):
    producto = Producto.query.get(producto_id)
    if not producto:
        return error_response('Producto no encontrado', 404)

    if DetalleMovimiento.query.filter_by(producto_id=producto_id).first():
        return error_response('No se puede eliminar: el producto tiene movimientos')

    db.session.delete(producto)
    db.session.commit()
    return success_response('Producto eliminado correctamente')

# Eliminar movimiento
@inventario_bp.route('/movimientos/<int:movimiento_id>', methods=['DELETE'])
@jwt_required()
def eliminar_movimiento(movimiento_id):
    movimiento = MovimientoInventario.query.get(movimiento_id)
    if not movimiento:
        return error_response('Movimiento no encontrado', 404)

    DetalleMovimiento.query.filter_by(movimiento_id=movimiento_id).delete()
    db.session.delete(movimiento)
    db.session.commit()
    return success_response('Movimiento eliminado correctamente')

# Ver existencias globales
@inventario_bp.route('/existencias', methods=['GET'])
@jwt_required()
def ver_existencias():
    inventario = InventarioSucursal.query.all()
    data = []

    for item in inventario:
        producto = Producto.query.get(item.producto_id)
        sucursal = Sucursal.query.get(item.sucursal_id)

        data.append({
            'producto_id': item.producto_id,
            'producto_nombre': producto.nombre if producto else 'Desconocido',
            'sucursal_id': item.sucursal_id,
            'sucursal_nombre': sucursal.sucursal if sucursal else 'Desconocida',
            'stock': item.stock,
            'unidad_medida': producto.unidad_medida if producto else ""
        })

    return jsonify(data), 200

# Listar todas las sucursales
@inventario_bp.route('/sucursales', methods=['GET'])
@jwt_required()
def listar_sucursales():
    sucursales = Sucursal.query.all()
    data = [{'id_sucursal': s.id_sucursal, 'sucursal': s.sucursal} for s in sucursales]
    return jsonify(data), 200

