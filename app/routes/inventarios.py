# C:\Users\Vladimir\Documents\Sistema tickets\app\routes\inventarios.py


from flask import Blueprint, request, jsonify
from app.extensions import db  # ✅
from app.models.inventario import (
    Producto, MovimientoInventario, DetalleMovimiento, InventarioSucursal
)


inventario_bp = Blueprint('inventario', __name__)
print("📦 Blueprint inventario_bp cargado correctamente")


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
        cantidad = p['cantidad']
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

        # Validación para evitar inventario negativo
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
        resultado.append({
            'producto_id': producto.id,
            'nombre': producto.nombre,
            'stock': item.stock,
            'unidad_medida': producto.unidad_medida
        })
    return jsonify(resultado), 200

# 5. Historial de movimientos
@inventario_bp.route('/movimientos', methods=['GET'])
def historial_movimientos():
    sucursal_id = request.args.get('sucursal_id', type=int)
    tipo = request.args.get('tipo_movimiento')  # entrada o salida

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

        resultado.append({
            'movimiento_id': m.id,
            'tipo': m.tipo_movimiento,
            'fecha': m.fecha.strftime('%Y-%m-%d %H:%M:%S'),
            'usuario_id': m.usuario_id,
            'sucursal_id': m.sucursal_id,
            'observaciones': m.observaciones,
            'productos': productos
        })

    return jsonify(resultado), 200

#6. Editar producto
@inventario_bp.route('/productos/<int:producto_id>', methods=['PUT'])
def editar_producto(producto_id):
    producto = Producto.query.get(producto_id)
    if not producto:
        return jsonify({'error': 'Producto no encontrado'}), 404

    data = request.get_json()

    nuevo_nombre = data.get('nombre')
    if not nuevo_nombre or not data.get('categoria'):
        return jsonify({'error': 'Nombre y categoría son obligatorios'}), 400

    # Verificar que no se repita el nombre con otro producto
    duplicado = Producto.query.filter(Producto.nombre == nuevo_nombre, Producto.id != producto_id).first()
    if duplicado:
        return jsonify({'error': 'Ya existe otro producto con ese nombre'}), 400

    producto.nombre = nuevo_nombre
    producto.descripcion = data.get('descripcion', producto.descripcion)
    producto.unidad_medida = data.get('unidad_medida', producto.unidad_medida)
    producto.categoria = data.get('categoria', producto.categoria)
    producto.subcategoria = data.get('subcategoria', producto.subcategoria)

    db.session.commit()
    return jsonify({'message': 'Producto actualizado correctamente'}), 200

#7. Eliminar producto (borrado real; opcional: podríamos hacer borrado lógico)
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


#8. Resumen de stock total por producto (todas las sucursales)
@inventario_bp.route('/stock-total', methods=['GET'])
def stock_total():
    inventario = db.session.query(
        Producto.id,
        Producto.nombre,
        Producto.unidad_medida,
        db.func.sum(InventarioSucursal.stock).label('stock_total')
    ).join(InventarioSucursal, InventarioSucursal.producto_id == Producto.id)\
     .group_by(Producto.id)\
     .all()

    resultado = [{
        'producto_id': p.id,
        'nombre': p.nombre,
        'unidad_medida': p.unidad_medida,
        'stock_total': int(p.stock_total)
    } for p in inventario]

    return jsonify(resultado), 200


#9. Resumen de entradas/salidas por producto
@inventario_bp.route('/resumen-movimientos', methods=['GET'])
def resumen_movimientos():
    resumen = db.session.query(
        Producto.id,
        Producto.nombre,
        Producto.unidad_medida,
        db.func.sum(
            db.case(
                (MovimientoInventario.tipo_movimiento == 'entrada', DetalleMovimiento.cantidad),
                else_=0
            )
        ).label('total_entradas'),
        db.func.sum(
            db.case(
                (MovimientoInventario.tipo_movimiento == 'salida', DetalleMovimiento.cantidad),
                else_=0
            )
        ).label('total_salidas')
    ).join(DetalleMovimiento, DetalleMovimiento.producto_id == Producto.id)\
     .join(MovimientoInventario, MovimientoInventario.id == DetalleMovimiento.movimiento_id)\
     .group_by(Producto.id)\
     .all()

    resultado = [{
        'producto_id': p.id,
        'nombre': p.nombre,
        'unidad_medida': p.unidad_medida,
        'total_entradas': int(p.total_entradas or 0),
        'total_salidas': int(p.total_salidas or 0)
    } for p in resumen]

    return jsonify(resultado), 200
