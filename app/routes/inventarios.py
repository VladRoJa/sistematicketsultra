# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\inventarios.py


from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.inventario import (
    Producto, MovimientoInventario, DetalleMovimiento, InventarioSucursal
)
from app.models.user_model import UserORM

from app.models.sucursal_model import Sucursal


inventario_bp = Blueprint('inventario', __name__)
print("📦 Blueprint inventario_bp cargado correctamente")


@inventario_bp.route('/productos/<int:producto_id>', methods=['OPTIONS'])
def options_producto(producto_id):
    return '', 200


# prueba ping pong
@inventario_bp.route('/ping', methods=['GET'])
def ping():
    return jsonify({'pong': True}), 200

# 1. Crear producto
@inventario_bp.route('/productos', methods=['POST'])
def crear_producto():
    data = request.get_json()

    if not data.get('nombre') or not data.get('categoria'):
        return jsonify({'error': 'Nombre y categoría son obligatorios'}), 400

    producto_existente = Producto.query.filter_by(nombre=data['nombre']).first()
    if producto_existente:
        return jsonify({'error': 'Ya existe un producto con ese nombre'}), 400

    producto = Producto(
        nombre=data['nombre'],
        descripcion=data.get('descripcion'),
        unidad_medida=data.get('unidad_medida'),
        categoria=data.get('categoria'),
        subcategoria=data.get('subcategoria')
    )
    db.session.add(producto)
    db.session.commit()
    return jsonify({'message': 'Producto creado correctamente', 'producto_id': producto.id}), 201

# 2. Obtener todos los productos
@inventario_bp.route('/productos', methods=['GET'])
def obtener_productos():
    productos = Producto.query.all()
    resultado = [{
        'id': p.id,
        'nombre': p.nombre,
        'unidad_medida': p.unidad_medida,
        'categoria': p.categoria
    } for p in productos]
    return jsonify(resultado), 200

# 3. Registrar entrada/salida de productos
@inventario_bp.route('/movimientos', methods=['POST'])
def registrar_movimiento():
    data = request.get_json()
    tipo = data.get('tipo_movimiento')
    sucursal_id = data.get('sucursal_id')
    usuario_id = data.get('usuario_id')
    observaciones = data.get('observaciones', '')
    productos = data.get('productos', [])

    if not productos or tipo not in ['entrada', 'salida']:
        return jsonify({'error': 'Datos inválidos'}), 400

    movimiento = MovimientoInventario(
        tipo_movimiento=tipo,
        sucursal_id=sucursal_id,
        usuario_id=usuario_id,
        observaciones=observaciones
    )
    db.session.add(movimiento)
    db.session.commit()

    for p in productos:
        producto_id = p['producto_id']
        try:
            cantidad = int(p['cantidad'])
        except (ValueError, TypeError):
            return jsonify({'error': f'Cantidad inválida para el producto ID {p.get("producto_id")}' }), 400

        unidad = p['unidad_medida']

        detalle = DetalleMovimiento(
            movimiento_id=movimiento.id,
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
        elif tipo == 'salida':
            if inventario.stock < cantidad:
                db.session.rollback()
                return jsonify({'error': f'Stock insuficiente para el producto ID {producto_id}'}), 400
            inventario.stock -= cantidad

    db.session.commit()
    return jsonify({'message': 'Movimiento registrado correctamente', 'movimiento_id': movimiento.id}), 201

# 4. Consultar inventario por sucursal

@inventario_bp.route('/sucursal/<int:sucursal_id>', methods=['GET'])
def obtener_inventario_por_sucursal(sucursal_id):
    inventario = InventarioSucursal.query.filter_by(sucursal_id=sucursal_id).all()
    resultado = []
    for item in inventario:
        producto = Producto.query.get(item.producto_id)

        # Buscar la fecha del último movimiento
        ultimo_movimiento = db.session.query(MovimientoInventario.fecha).join(DetalleMovimiento).filter(
            DetalleMovimiento.producto_id == item.producto_id,
            MovimientoInventario.sucursal_id == sucursal_id
        ).order_by(MovimientoInventario.fecha.desc()).first()

        resultado.append({
            'producto_id': producto.id,
            'nombre': producto.nombre,
            'stock': item.stock,
            'unidad_medida': producto.unidad_medida,
            'ultimo_movimiento': ultimo_movimiento[0].strftime('%d/%m/%y %H:%M') if ultimo_movimiento else 'N/A'
        })

    return jsonify(resultado), 200


# 5. Historial de movimientos
@inventario_bp.route('/movimientos', methods=['GET'])
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

        productos = []
        for d in detalles:
            producto = Producto.query.get(d.producto_id)
            productos.append({
                'producto_id': d.producto_id,
                'nombre': producto.nombre if producto else 'Desconocido',
                'cantidad': d.cantidad,
                'unidad_medida': d.unidad_medida
            })

        sucursal = Sucursal.query.get(m.sucursal_id)
        sucursal_nombre = sucursal.sucursal if sucursal else 'Desconocida'

        usuario = UserORM.query.get(m.usuario_id)
        usuario_nombre = usuario.username if usuario else 'Desconocido'

        resultado.append({
            'movimiento_id': m.id,
            'tipo': m.tipo_movimiento,
            'fecha': m.fecha.strftime('%d/%m/%y %H:%M'),
            'usuario_id': m.usuario_id,
            'usuario_nombre': usuario_nombre,
            'sucursal_id': m.sucursal_id,
            'sucursal_nombre': sucursal_nombre,
            'observaciones': m.observaciones,
            'productos': productos
        })

    return jsonify(resultado), 200

# 6. Editar producto
@inventario_bp.route('/productos/<int:producto_id>', methods=['PUT'])
def editar_producto(producto_id):
    producto = Producto.query.get(producto_id)
    if not producto:
        return jsonify({'error': 'Producto no encontrado'}), 404

    data = request.get_json()
    nuevo_nombre = data.get('nombre')
    
    if not nuevo_nombre or not data.get('categoria'):
        return jsonify({'error': 'Nombre y categoría son obligatorios'}), 400

    duplicado = Producto.query.filter(
        Producto.nombre == nuevo_nombre,
        Producto.id != producto_id
    ).first()

    if duplicado:
        return jsonify({'error': 'Ya existe otro producto con ese nombre'}), 400

    producto.nombre = nuevo_nombre
    producto.descripcion = data.get('descripcion', producto.descripcion)
    producto.unidad_medida = data.get('unidad_medida', producto.unidad_medida)
    producto.categoria = data.get('categoria', producto.categoria)
    producto.subcategoria = data.get('subcategoria', producto.subcategoria)

    db.session.commit()
    return jsonify({'message': 'Producto actualizado correctamente'}), 200

#7. Eliminar producto
@inventario_bp.route('/productos/<int:producto_id>', methods=['DELETE'])
def eliminar_producto(producto_id):
    producto = Producto.query.get(producto_id)
    if not producto:
        return jsonify({'error': 'Producto no encontrado'}), 404

    relacionado = DetalleMovimiento.query.filter_by(producto_id=producto_id).first()
    if relacionado:
        return jsonify({'error': 'No se puede eliminar: el producto tiene movimientos registrados'}), 400

    db.session.delete(producto)
    db.session.commit()
    return jsonify({'message': 'Producto eliminado correctamente'}), 200

#8. Eliminar movimiento
@inventario_bp.route('/movimientos/<int:movimiento_id>', methods=['DELETE'])
def eliminar_movimiento(movimiento_id):
    movimiento = MovimientoInventario.query.get(movimiento_id)
    if not movimiento:
        return jsonify({'error': 'Movimiento no encontrado'}), 404

    # Borrar detalles primero (por la FK)
    DetalleMovimiento.query.filter_by(movimiento_id=movimiento_id).delete()

    # Luego borrar movimiento principal
    db.session.delete(movimiento)
    db.session.commit()
    return jsonify({'message': 'Movimiento eliminado correctamente'}), 200

#9. Existencias

@inventario_bp.route('/existencias', methods=['GET'])
def ver_existencias():
    inventario = InventarioSucursal.query.all()
    resultado = []

    for item in inventario:
        producto = Producto.query.get(item.producto_id)
        sucursal = Sucursal.query.get(item.sucursal_id)

        resultado.append({
            'producto_id': item.producto_id,
            'producto_nombre': producto.nombre if producto else 'Desconocido',
            'sucursal_id': item.sucursal_id,
            'sucursal_nombre': sucursal.sucursal if sucursal else 'Desconocida',
            'stock': item.stock,
            'unidad_medida': producto.unidad_medida if producto else ''
        })

    return jsonify(resultado), 200



# Ruta para obtener todas las sucursales
@inventario_bp.route('/sucursales', methods=['GET'])
def listar_sucursales():
    sucursales = Sucursal.query.all()
    resultado = [{
        'id_sucursal': s.id_sucursal,
        'sucursal': s.sucursal
    } for s in sucursales]
    return jsonify(resultado), 200

# Ruta para obtener el stock total de un producto en una sucursal
@inventario_bp.route('/stock-total', methods=['GET'])
def obtener_stock_total():
    inventario = InventarioSucursal.query.all()
    resultado = []

    for item in inventario:
        producto = Producto.query.get(item.producto_id)

        # Último movimiento global
        ultimo_movimiento = db.session.query(MovimientoInventario.fecha).join(DetalleMovimiento).filter(
            DetalleMovimiento.producto_id == item.producto_id
        ).order_by(MovimientoInventario.fecha.desc()).first()

        resultado.append({
            'producto_id': producto.id,
            'nombre': producto.nombre,
            'stock_total': item.stock,
            'unidad_medida': producto.unidad_medida,
            'ultimo_movimiento': ultimo_movimiento[0].strftime('%d/%m/%y %H:%M') if ultimo_movimiento else 'N/A'
        })

    return jsonify(resultado), 200
