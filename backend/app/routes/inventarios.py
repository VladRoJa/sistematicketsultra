# backend\app\routes\inventarios.py

import base64
from io import BytesIO
import io
import os
import tempfile
from flask import Blueprint, request, jsonify, send_file
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt_identity
import pandas as pd
import qrcode
from app. extensions import db
from app.models.catalogos import CategoriaInventario
from app.models.inventario import InventarioGeneral, MovimientoInventario, DetalleMovimiento, InventarioSucursal
from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.models.sucursal_model import Sucursal
from datetime import datetime
import pytz
from app.config import Config
from app. utils.error_handler import manejar_error
from app.models.sucursal_model import Sucursal
from app. utils.string_utils import normalizar_campo
from werkzeug.utils import secure_filename

inventario_bp = Blueprint('inventario', __name__, url_prefix='/api/inventario')

tz = pytz.timezone('America/Tijuana')

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


def _parse_int_nonneg(val, field_name):
    """
    Convierte a int y valida que sea >= 0.
    - Si val es None o '', regresa None (para campos opcionales).
    - Si no es convertible a int o es negativo, lanza ValueError con mensaje claro.
    """
    if val is None or (isinstance(val, str) and val.strip() == ''):
        return None
    try:
        n = int(val)
        if n < 0:
            raise ValueError(f"{field_name} no puede ser negativo")
        return n
    except Exception:
        raise ValueError(f"{field_name} debe ser un entero no negativo")


# Crear un nuevo inventario (producto/aparato/unificado)
@inventario_bp.route('/', methods=['POST'], strict_slashes=False)
@jwt_required()
def crear_inventario():
    try:
        data = request.get_json()
        if not data.get('nombre') or not data.get('categoria'):
            return error_response('Nombre y categoría son obligatorios')

        # Validar que NO exista otro producto con el mismo nombre y marca
        existe = InventarioGeneral.query.filter_by(
            nombre=data['nombre'].strip(),
            marca=data.get('marca', '').strip()
        ).first()
        if existe:
            return error_response('Ya existe un producto con ese nombre y marca')

        ahora = datetime.now(tz)
        codigo = normalizar_campo(data.get('codigo_interno')).upper()
                # --- Validaciones numéricas ---
        try:
            gasto_sem = _parse_int_nonneg(data.get('gasto_sem'), 'gasto_sem')
            gasto_mes = _parse_int_nonneg(data.get('gasto_mes'), 'gasto_mes')
            pedido_mes = _parse_int_nonneg(data.get('pedido_mes'), 'pedido_mes')
        except ValueError as ve:
            return error_response(str(ve))
        
        
        nuevo = InventarioGeneral(
            tipo=normalizar_campo(data.get('tipo', 'producto')),
            nombre=normalizar_campo(data['nombre']),
            descripcion=normalizar_campo(data.get('descripcion')),
            marca=normalizar_campo(data.get('marca')),
            proveedor=normalizar_campo(data.get('proveedor')),
            categoria=normalizar_campo(data.get('categoria')),
            unidad_medida=normalizar_campo(data.get('unidad_medida')),
            codigo_interno=codigo,
            no_equipo=normalizar_campo(data.get('no_equipo')),
            gasto_sem=gasto_sem,
            gasto_mes=gasto_mes,
            pedido_mes=pedido_mes,
            semana_pedido=normalizar_campo(data.get('semana_pedido')),
            fecha_inventario=ahora,
            grupo_muscular=normalizar_campo(data.get('grupo_muscular')),
            subcategoria=normalizar_campo(data.get('subcategoria', ''))  
            
        )


        db.session.add(nuevo)
        db.session.commit()
        return success_response('Producto creado correctamente', {'inventario_id': nuevo.id})

    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "crear_inventario")

# Obtener todo el inventario
@inventario_bp.route('/', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required()
def obtener_inventario():
    try:
        sucursal_id = request.args.get('sucursal_id', type=int)

        # ---- Helpers locales ----
        def _resolver_categoria(inv):
            """
            Regresa (categoria, subcategoria) usando SOLO el catálogo si hay FK.
            Si NO hay FK o la FK es inválida, cae a los campos legacy del inventario.
            """
            cat_id = getattr(inv, 'categoria_inventario_id', None)
            if cat_id:
                cat = CategoriaInventario.query.get(cat_id)
                if cat:
                    # SOLO catálogo
                    return (getattr(cat, 'nombre', '') or ''), (getattr(cat, 'subcategoria', '') or '')
                # FK inválida -> legacy
                return (inv.categoria or ''), (inv.subcategoria or '')
            # Sin FK -> legacy
            return (inv.categoria or ''), (inv.subcategoria or '')


        def descripcion_larga(inv, categoria_resuelta=None):
            partes = [
                inv.nombre,
                inv.marca,
                inv.proveedor,
                (categoria_resuelta if categoria_resuelta is not None else inv.categoria),
                f"ID:{inv.id}"
            ]
            return " - ".join([str(p) for p in partes if p])

        # ---------- Por sucursal ----------
        if sucursal_id:
            inventarios = InventarioSucursal.query.filter_by(sucursal_id=sucursal_id).all()
            data = []
            for inv_suc in inventarios:
                i = InventarioGeneral.query.get(inv_suc.inventario_id)
                if i:
                    categoria_res, subcategoria_res = _resolver_categoria(i)
                    data.append({
                        'id': i.id,
                        'nombre': i.nombre,
                        'descripcion': i.descripcion,
                        'marca': i.marca,
                        'proveedor': i.proveedor,
                        'categoria': categoria_res,                 # ✅ resuelta
                        'subcategoria': subcategoria_res,           # ✅ resuelta
                        'unidad_medida': i.unidad_medida,
                        'codigo_interno': i.codigo_interno,
                        'no_equipo': i.no_equipo,
                        'gasto_sem': i.gasto_sem,
                        'gasto_mes': i.gasto_mes,
                        'pedido_mes': i.pedido_mes,
                        'semana_pedido': i.semana_pedido,
                        'fecha_inventario': str(i.fecha_inventario) if i.fecha_inventario else None,
                        'grupo_muscular': i.grupo_muscular,
                        'stock': inv_suc.stock,
                        'descripcion_larga': descripcion_larga(i, categoria_res),
                        'categoria_inventario_id': getattr(i, 'categoria_inventario_id', None),
                    })
            return jsonify(data), 200

        # ---------- Global ----------
        inventario = InventarioGeneral.query.all()
        data = []
        for i in inventario:
            categoria_res, subcategoria_res = _resolver_categoria(i)
            data.append({
                'id': i.id,
                # 'tipo': i.tipo,  # ❌ Eliminado: dejamos de exponer 'tipo'
                'nombre': i.nombre,
                'descripcion': i.descripcion,
                'marca': i.marca,
                'proveedor': i.proveedor,
                'categoria': categoria_res,                 # ✅ resuelta
                'subcategoria': subcategoria_res,           # ✅ resuelta
                'unidad_medida': i.unidad_medida,
                'codigo_interno': i.codigo_interno,
                'no_equipo': i.no_equipo,
                'gasto_sem': i.gasto_sem,
                'gasto_mes': i.gasto_mes,
                'pedido_mes': i.pedido_mes,
                'semana_pedido': i.semana_pedido,
                'fecha_inventario': str(i.fecha_inventario) if i.fecha_inventario else None,
                'grupo_muscular': i.grupo_muscular,
                'descripcion_larga': descripcion_larga(i, categoria_res),
                'categoria_inventario_id': getattr(i, 'categoria_inventario_id', None),
            })
        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "obtener_inventario")


# Registrar entrada/salida de inventario
@inventario_bp.route('/movimientos', methods=['POST'], strict_slashes=False)
@jwt_required()
def registrar_movimiento():
    try:
        data = request.get_json()
        tipo = data.get('tipo_movimiento')
        sucursal_id = data.get('sucursal_id')
        usuario_id = data.get('usuario_id')
        inventarios = data.get('inventarios', [])
        observaciones = data.get('observaciones', '')

        if tipo not in ['entrada', 'salida'] or not inventarios:
            return error_response('Datos inválidos')

        nuevo_movimiento = MovimientoInventario(
            tipo_movimiento=tipo,
            sucursal_id=sucursal_id,
            usuario_id=usuario_id,
            observaciones=observaciones,
            fecha=datetime.now(tz)
        )
        db.session.add(nuevo_movimiento)
        db.session.flush()  # Obtener ID antes de commit

        for p in inventarios:
            inventario_id = p['inventario_id']
            cantidad = int(p['cantidad'])

            # Cargar inventario para conocer sus unidades
            inv = InventarioGeneral.query.get(inventario_id)
            if not inv:
                db.session.rollback()
                return error_response(f'Inventario {inventario_id} no existe')

            # Unidad capturada en el movimiento (por defecto la unidad base)
            unidad_mov = normalizar_campo(p.get('unidad_medida')) or inv.unidad_medida

            # Calcular factor de conversión
            factor = 1
            if inv.unidad_compra and inv.factor_compra and inv.factor_compra > 1:
                if unidad_mov == normalizar_campo(inv.unidad_compra):
                    factor = inv.factor_compra

            # Convertir a unidad base
            cantidad_base = cantidad * factor

            # Guardar siempre en unidad base
            detalle = DetalleMovimiento(
                movimiento_id=nuevo_movimiento.id,
                inventario_id=inventario_id,
                cantidad=cantidad_base,
                unidad_medida=inv.unidad_medida
            )
            db.session.add(detalle)

            # Control por sucursal
            inventario_sucursal = InventarioSucursal.query.filter_by(
                inventario_id=inventario_id,
                sucursal_id=sucursal_id
            ).first()

            if not inventario_sucursal:
                inventario_sucursal = InventarioSucursal(
                    inventario_id=inventario_id,
                    sucursal_id=sucursal_id,
                    stock=0
                )
                db.session.add(inventario_sucursal)

            if tipo == 'entrada':
                inventario_sucursal.stock += cantidad_base
            else:  # salida
                if inventario_sucursal.stock < cantidad_base:
                    db.session.rollback()
                    return error_response(f'Stock insuficiente para el inventario {inventario_id}')
                inventario_sucursal.stock -= cantidad_base


        db.session.commit()
        return success_response('Movimiento registrado correctamente', {'movimiento_id': nuevo_movimiento.id})

    except Exception as e:
        return manejar_error(e, "registrar_movimiento")

# Ver historial de movimientos
@inventario_bp.route('/movimientos', methods=['GET'], strict_slashes=False)
@jwt_required()
def historial_movimientos():
    try:
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
            inventarios = [{
                'inventario_id': d.inventario_id,
                'cantidad': d.cantidad,
                'unidad_medida': d.unidad_medida,
                'codigo_interno': d.inventario.codigo_interno,
                'no_equipo': d.inventario.no_equipo
            } for d in detalles]

            sucursal = Sucursal.query.get(m.sucursal_id)
            usuario = UserORM.query.get(m.usuario_id)

            resultado.append({
                'id': m.id,
                'tipo': m.tipo_movimiento,
                'fecha': m.fecha.strftime('%d/%m/%Y %H:%M'), 
                'usuario': usuario.username if usuario else "Desconocido",
                'usuario_id': m.usuario_id,
                'sucursal': sucursal.sucursal if sucursal else "Desconocida",  
                'sucursal_id': m.sucursal_id,
                'observaciones': m.observaciones,
                'inventarios': inventarios
            })

        return jsonify(resultado), 200

    except Exception as e:
        return manejar_error(e, "historial_movimientos")

# Ver existencias globales
@inventario_bp.route('/existencias', methods=['GET'], strict_slashes=False)
@jwt_required()
def ver_existencias():
    try:
        def descripcion_larga(inv):
            partes = [
                inv.nombre,
                inv.marca,
                inv.proveedor,
                inv.categoria,
                f"ID:{inv.id}"
            ]
            return " - ".join([str(p) for p in partes if p])

        inventario = InventarioSucursal.query.all()
        data = []

        for item in inventario:
            inventario_general = InventarioGeneral.query.get(item.inventario_id)
            sucursal = Sucursal.query.get(item.sucursal_id)

            data.append({
                'inventario_id': item.inventario_id,
                'nombre': inventario_general.nombre if inventario_general else 'Desconocido',
                'categoria': inventario_general.categoria if inventario_general else '',
                'tipo': inventario_general.tipo if inventario_general else '',
                'marca': inventario_general.marca if inventario_general else '',
                'proveedor': inventario_general.proveedor if inventario_general else '',
                'unidad_medida': inventario_general.unidad_medida if inventario_general else "",
                'sucursal_id': item.sucursal_id,
                'sucursal_nombre': sucursal.sucursal if sucursal else 'Desconocida',
                'stock': item.stock,
                'descripcion_larga': descripcion_larga(inventario_general) if inventario_general else ''
            })

        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "ver_existencias")

# Listar todas las sucursales
@inventario_bp.route('/sucursales', methods=['GET'], strict_slashes=False)
@jwt_required()
def listar_sucursales():
    try:
        sucursales = Sucursal.query.all()
        data = [{'sucursal_id': s.sucursal_id, 'sucursal': s.sucursal} for s in sucursales]
        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "listar_sucursales")

# Editar inventario general
@inventario_bp.route('/<int:inventario_id>', methods=['PUT'], strict_slashes=False)
@jwt_required()
def editar_inventario(inventario_id):
    try:
        inventario = InventarioGeneral.query.get(inventario_id)
        if not inventario:
            return error_response('Inventario no encontrado', 404)

        data = request.get_json()
        campos = [
            'tipo', 'nombre', 'descripcion', 'marca', 'proveedor',
            'categoria', 'unidad_medida',
            'codigo_interno', 'no_equipo', 'gasto_sem', 'gasto_mes',
            'pedido_mes', 'semana_pedido', 'subcategoria','unidad_compra', 'factor_compra'
        ]
        for campo in campos:
            if campo in data:
                valor = data[campo]
                # Normaliza strings
                if isinstance(valor, str):
                    valor = normalizar_campo(valor)
                    if campo == 'codigo_interno' and valor:
                        valor = valor.upper()

                # Valida numéricos no negativos
                if campo in ['gasto_sem', 'gasto_mes', 'pedido_mes']:
                    try:
                        valor = _parse_int_nonneg(valor, campo)
                    except ValueError as ve:
                        return error_response(str(ve))
                    
                if campo == 'factor_compra':
                    try:
                        valor = _parse_int_nonneg(valor, campo)
                    except ValueError as ve:
                        return error_response(str(ve))
                    if not valor or valor < 1:
                        valor = 1

                setattr(inventario, campo, valor)


        inventario.fecha_inventario = datetime.now(tz)
        db.session.commit()
        return success_response('Producto actualizado correctamente')
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "editar_inventario")

# Eliminar inventario general
@inventario_bp.route('/<int:inventario_id>', methods=['DELETE'], strict_slashes=False)
@jwt_required()
def eliminar_inventario(inventario_id):
    try:
        inventario = InventarioGeneral.query.get(inventario_id)
        if not inventario:
            return error_response('Inventario no encontrado', 404)

        # Verifica que no haya movimientos asociados antes de borrar
        if DetalleMovimiento.query.filter_by(inventario_id=inventario_id).first():
            return error_response('No se puede eliminar: el inventario tiene movimientos registrados')

        db.session.delete(inventario)
        db.session.commit()
        return success_response('Inventario eliminado correctamente')

    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "eliminar_inventario")

@inventario_bp.route('/<int:inventario_id>', methods=['GET'], strict_slashes=False)
@jwt_required()
def obtener_inventario_por_id(inventario_id):
    try:
        i = InventarioGeneral.query.get(inventario_id)
        if not i:
            return error_response('Inventario no encontrado', 404)

        data = {
            'id': i.id,
            'tipo': i.tipo,
            'nombre': i.nombre,
            'descripcion': i.descripcion,
            'marca': i.marca,
            'proveedor': i.proveedor,
            'categoria': i.categoria,
            'unidad_medida': i.unidad_medida, 
            'codigo_interno': i.codigo_interno,
            'no_equipo': i.no_equipo,
            'gasto_sem': i.gasto_sem,
            'gasto_mes': i.gasto_mes,
            'pedido_mes': i.pedido_mes,
            'semana_pedido': i.semana_pedido,
            'fecha_inventario': str(i.fecha_inventario) if i.fecha_inventario else None
        }
        return jsonify(data), 200
    except Exception as e:
        return manejar_error(e, "obtener_inventario_por_id")

@inventario_bp.route('/buscar', methods=['GET'], strict_slashes=False)
@jwt_required()
def buscar_inventario():
    try:
        nombre = request.args.get('nombre', '').strip()
        categoria = request.args.get('categoria', '').strip()
        tipo = request.args.get('tipo', '').strip()

        query = InventarioGeneral.query

        if nombre:
            query = query.filter(InventarioGeneral.nombre.ilike(f"%{nombre}%"))
        if categoria:
            query = query.filter(InventarioGeneral.categoria.ilike(f"%{categoria}%"))
        if tipo:
            query = query.filter(InventarioGeneral.tipo.ilike(f"%{tipo}%"))

        inventario = query.order_by(InventarioGeneral.nombre).all()
        data = [{
            'id': i.id,
            'tipo': i.tipo,
            'nombre': i.nombre,
            'descripcion': i.descripcion,
            'marca': i.marca,
            'proveedor': i.proveedor,
            'categoria': i.categoria,
            'unidad_medida': i.unidad_medida, 
            'codigo_interno': i.codigo_interno,
            'no_equipo': i.no_equipo,
            'gasto_sem': i.gasto_sem,
            'gasto_mes': i.gasto_mes,
            'pedido_mes': i.pedido_mes,
            'semana_pedido': i.semana_pedido,
            'fecha_inventario': str(i.fecha_inventario) if i.fecha_inventario else None
        } for i in inventario]
        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "buscar_inventario")
    
    
@inventario_bp.route('/movimientos/<int:id>', methods=['DELETE'], strict_slashes=False)
@jwt_required()
def eliminar_movimiento(id):
    try:
        mov = MovimientoInventario.query.get(id)
        if not mov:
            return jsonify({"error": "Movimiento no encontrado"}), 404

        # Ajustar stock antes de eliminar detalles
        for det in mov.detalles:
            inventario_sucursal = InventarioSucursal.query.filter_by(
                inventario_id=det.inventario_id,
                sucursal_id=mov.sucursal_id
            ).first()
            if inventario_sucursal:
                if mov.tipo_movimiento == 'entrada':
                    inventario_sucursal.stock = max(0, inventario_sucursal.stock - det.cantidad)
                elif mov.tipo_movimiento == 'salida':
                    inventario_sucursal.stock += det.cantidad

        # Elimina los detalles y el movimiento
        for det in mov.detalles:
            db.session.delete(det)
        db.session.delete(mov)
        db.session.commit()
        return jsonify({"mensaje": "Movimiento eliminado correctamente"}), 200
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "eliminar_movimiento")

@inventario_bp.route('/equipos', methods=['GET'], strict_slashes=False)
@jwt_required()
def listar_equipos():
    try:
        user_id = get_jwt_identity()
        user = UserORM.query.get(user_id)
        if not user:
            return error_response('Usuario no encontrado', 404)

        tipo = (request.args.get('tipo') or '').strip().lower()
        # Mapea todos los posibles valores recibidos a lo que existe en tu base
        if tipo in ['aparato', 'aparatos']:
            tipo = 'aparatos'
        elif tipo in ['sistema', 'sistemas', 'dispositivo', 'dispositivos']:
            tipo = 'dispositivos'  # AJUSTA a tu valor real en la base si es "dispositivos"
        else:
            tipo = ''
        sucursal_id = request.args.get('sucursal_id', type=int)

        query = InventarioGeneral.query
        query = query.filter(InventarioGeneral.codigo_interno.isnot(None))
        if tipo:
            query = query.filter(db.func.lower(InventarioGeneral.tipo) == tipo)

        # Filtro por sucursal:
        if not (user.rol == "ADMINISTRADOR" or user.sucursal_id == 1000 or user.sucursal_id == 100):
            query = query.join(InventarioSucursal).filter(InventarioSucursal.sucursal_id == user.sucursal_id)
        elif sucursal_id:
            query = query.join(InventarioSucursal).filter(InventarioSucursal.sucursal_id == sucursal_id)

        equipos = query.order_by(InventarioGeneral.nombre.asc()).all()
        data = []
        for eq in equipos:
            data.append({
                "id": eq.id,
                "nombre": eq.nombre,
                "codigo_interno": eq.codigo_interno,
                "tipo": eq.tipo,
                "marca": eq.marca,
                "categoria": eq.categoria,
                "sucursal_ids": [inv.sucursal_id for inv in eq.inventarios_sucursal]
            })

        return jsonify(data), 200
    except Exception as e:
        return manejar_error(e, "listar_equipos")


@inventario_bp.route('/equipos-historial', methods=['GET'], strict_slashes=False)
@jwt_required()
def equipos_con_historial():
    """
    Devuelve todos los equipos que tienen al menos un ticket (historial).
    Puedes filtrar por tipo=aparato/sistema y/o sucursal_id.
    """
    try:
        user = UserORM.get_by_id(get_jwt_identity())
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        tipo = request.args.get('tipo')  # "aparato", "sistema" o None
        sucursal_id = request.args.get('sucursal_id', type=int)

        # Construye el query base
        q = db.session.query(InventarioGeneral).join(Ticket, InventarioGeneral.id == Ticket.aparato_id)
        
        if tipo:
            q = q.filter(InventarioGeneral.tipo == tipo)
        if not (user.rol == "ADMINISTRADOR" or user.sucursal_id == 1000 or user.sucursal_id == 100):
            q = q.join(Ticket).filter(Ticket.sucursal_id == user.sucursal_id)
        elif sucursal_id:
            q = q.join(Ticket).filter(Ticket.sucursal_id == sucursal_id)

        # Distintos (porque puede haber muchos tickets por equipo)
        equipos = q.distinct().all()

        data = [{
            "id": eq.id,
            "nombre": eq.nombre,
            "codigo_interno": eq.codigo_interno,
            "tipo": eq.tipo,
            "categoria": eq.categoria,
            "marca": eq.marca,
            "grupo_muscular": eq.grupo_muscular
        } for eq in equipos]

        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "equipos_con_historial")


@inventario_bp.route('/<int:equipo_id>/historial', methods=['GET'], strict_slashes=False)
@jwt_required()
def historial_equipo(equipo_id):
    """
    Devuelve el historial completo de tickets para el equipo/aparato dado.
    """
    try:
        user = UserORM.get_by_id(get_jwt_identity())
        if not user:
            return jsonify({"mensaje": "Usuario no encontrado"}), 404

        query = Ticket.query.filter(Ticket.aparato_id == equipo_id)

        if not (user.rol == "ADMINISTRADOR" or user.sucursal_id == 1000 or user.sucursal_id == 100):
            query = query.filter(Ticket.sucursal_id == user.sucursal_id)

        tickets = query.order_by(Ticket.fecha_creacion.desc()).all()

        data = []
        for t in tickets:
            data.append({
                "id": t.id,
                "descripcion": t.descripcion,
                "estado": t.estado,
                "fecha_creacion": t.fecha_creacion.isoformat() if t.fecha_creacion else None,
                "fecha_finalizado": t.fecha_finalizado.isoformat() if t.fecha_finalizado else None,
                "fecha_solucion": t.fecha_solucion.isoformat() if t.fecha_solucion else None,
                "username": t.username,
                "asignado_a": t.asignado_a,
                "problema_detectado": t.problema_detectado,
                "necesita_refaccion": t.necesita_refaccion,
                "descripcion_refaccion": t.descripcion_refaccion,
                "url_evidencia": t.url_evidencia,
                "historial_fechas": t.historial_fechas,
                "sucursal_id": t.sucursal_id
            })

        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "historial_equipo")


# @inventario_bp.route('/equipos', methods=['GET'], strict_slashes=False)
# @jwt_required()
# def obtener_equipos():
#     """
#     Devuelve los equipos por sucursal y tipo.
#     Parámetros opcionales:
#     - sucursal_id: ID de la sucursal.
#     - tipo: 'aparato' o 'sistema'.
#     """
#     try:
#         user = UserORM.get_by_id(get_jwt_identity())
#         if not user:
#             return jsonify({"mensaje": "Usuario no encontrado"}), 404

#         sucursal_id = request.args.get('sucursal_id', type=int)
#         tipo = (request.args.get('tipo') or '').strip().lower()
#         # Mapea todos los posibles valores recibidos a lo que existe en tu base
#         if tipo in ['aparato', 'aparatos']:
#             tipo = 'aparatos'
#         elif tipo in ['sistema', 'sistemas', 'dispositivo', 'dispositivos']:
#             tipo = 'dispositivos'
#         else:
#             tipo = ''

#         query = InventarioSucursal.query

#         # Si no es admin, restringe a la sucursal del usuario
#         if not (user.rol == "ADMINISTRADOR" or user.sucursal_id == 1000 or user.sucursal_id == 100):
#             query = query.filter_by(sucursal_id=user.sucursal_id)
#         elif sucursal_id:
#             query = query.filter_by(sucursal_id=sucursal_id)

#         equipos = query.all()

#         resultado = []
#         for e in equipos:
#             # Compara ambos en minúsculas (por si acaso)
#             if tipo and (e.inventario.tipo or '').strip().lower() != tipo:
#                 continue
#             resultado.append({
#                 "id": e.inventario.id,
#                 "nombre": e.inventario.nombre,
#                 "codigo_interno": e.inventario.codigo_interno,
#                 "categoria": e.inventario.categoria,
#                 "marca": e.inventario.marca,
#                 "stock": e.stock,
#                 "sucursal_id": e.sucursal_id,
#                 "tipo": e.inventario.tipo,
#                 "no_equipo": e.inventario.no_equipo,
#             })

#         return jsonify(resultado), 200

#     except Exception as e:
#         return manejar_error(e, "obtener_equipos")



@inventario_bp.route('/listar', methods=['GET'], strict_slashes=False)
@jwt_required()
def listar_inventario_filtrado():
    """
    Devuelve todos los productos/activos filtrados por tipo y sucursal.
    Parámetros opcionales:
        - tipo (str): 'aparato', 'sistema' (case-insensitive)
        - sucursal_id (int): filtra por sucursal específica
    """
    try:
        tipo = request.args.get('tipo', '').strip().lower()
        sucursal_id = request.args.get('sucursal_id', type=int)

        query = InventarioGeneral.query

        if tipo:
            query = query.filter(InventarioGeneral.tipo.ilike(f'%{tipo}%'))

        # Si se quiere filtrar por sucursal, devolver SOLO los que tengan stock > 0 en esa sucursal
        if sucursal_id:
            ids_en_sucursal = [inv.inventario_id for inv in InventarioSucursal.query.filter_by(sucursal_id=sucursal_id).filter(InventarioSucursal.stock > 0).all()]
            query = query.filter(InventarioGeneral.id.in_(ids_en_sucursal))

        # Si no eres admin, filtra solo por tu sucursal
        user = UserORM.get_by_id(get_jwt_identity())
        if user and not (user.rol == "ADMINISTRADOR" or user.sucursal_id == 1000 or user.sucursal_id == 100):
            if not sucursal_id:
                ids_en_sucursal = [inv.inventario_id for inv in InventarioSucursal.query.filter_by(sucursal_id=user.sucursal_id).filter(InventarioSucursal.stock > 0).all()]
                query = query.filter(InventarioGeneral.id.in_(ids_en_sucursal))

        inventarios = query.order_by(InventarioGeneral.nombre).all()
        data = [{
            'id': i.id,
            'nombre': i.nombre,
            'codigo_interno': i.codigo_interno,
            'tipo': i.tipo,
            'categoria': i.categoria,
            'marca': i.marca,
            'grupo_muscular': getattr(i, 'grupo_muscular', None),
            'stock': sum([inv.stock for inv in i.inventarios_sucursal]),
        } for i in inventarios]

        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "listar_inventario_filtrado")

@inventario_bp.route('/<int:inventario_id>/qr', methods=['GET'], strict_slashes=False)
@jwt_required()
def generar_qr_inventario(inventario_id):
    """
    Devuelve un QR PNG con los datos de identificación del aparato/sistema.
    """

    try:
        inv = InventarioGeneral.query.get(inventario_id)
        if not inv:
            return error_response('Inventario no encontrado', 404)

        # Codificamos lo mínimo necesario para lookup rápido
        qr_data = {
            "inventario_id": inv.id,
            "codigo_interno": inv.codigo_interno,
            "tipo": inv.tipo,
        }

        # QR codifica JSON
        import json
        qr_str = json.dumps(qr_data)
        img = qrcode.make(qr_str)
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        return jsonify({
            'qr_base64': img_b64,
            'inventario_id': inv.id,
            'codigo_interno': inv.codigo_interno,
            'nombre': inv.nombre,
            'tipo': inv.tipo,
        }), 200
    except Exception as e:
        return manejar_error(e, "generar_qr_inventario")


@inventario_bp.route('/buscar-por-codigo', methods=['GET'], strict_slashes=False)
@jwt_required()
def buscar_por_codigo():
    """
    Busca y devuelve un inventario por código interno (escaneado de QR)
    """
    try:
        codigo = request.args.get('codigo')
        if not codigo:
            return error_response('Código interno es requerido')
        inv = InventarioGeneral.query.filter_by(codigo_interno=codigo.upper()).first()
        if not inv:
            return error_response('Inventario no encontrado', 404)
        return jsonify({
            'id': inv.id,
            'nombre': inv.nombre,
            'codigo_interno': inv.codigo_interno,
            'tipo': inv.tipo,
            'categoria': inv.categoria,
            'marca': inv.marca,
            'grupo_muscular': getattr(inv, 'grupo_muscular', None),
        }), 200
    except Exception as e:
        return manejar_error(e, "buscar_por_codigo")


@inventario_bp.route('/<int:inventario_id>/historial', methods=['GET'], strict_slashes=False)
@jwt_required()
def historial_aparato(inventario_id):
    """
    Devuelve el historial de movimientos y tickets asociados a un aparato/sistema.
    """

    try:
        inv = InventarioGeneral.query.get(inventario_id)
        if not inv:
            return error_response('Inventario no encontrado', 404)

        # Movimientos de inventario
        movimientos = DetalleMovimiento.query.filter_by(inventario_id=inventario_id).all()
        movs = [{
            "fecha": m.movimiento.fecha.strftime('%d/%m/%Y %H:%M'),
            "tipo": m.movimiento.tipo_movimiento,
            "usuario_id": m.movimiento.usuario_id,
            "sucursal_id": m.movimiento.sucursal_id,
            "cantidad": m.cantidad,
            "unidad_medida": m.unidad_medida,
            "observaciones": m.movimiento.observaciones
        } for m in movimientos]

        # Tickets asociados a este aparato
        tickets = Ticket.query.filter_by(aparato_id=inventario_id).order_by(Ticket.fecha_creacion.desc()).all()
        tks = [{
            "id": t.id,
            "descripcion": t.descripcion,
            "estado": t.estado,
            "fecha_creacion": t.fecha_creacion.strftime('%d/%m/%Y %H:%M'),
            "fecha_solucion": t.fecha_solucion.strftime('%d/%m/%Y %H:%M') if t.fecha_solucion else None,
            "categoria": t.categoria,
            "subcategoria": t.subcategoria,
            "problema_detectado": t.problema_detectado,
            "necesita_refaccion": t.necesita_refaccion,
            "descripcion_refaccion": t.descripcion_refaccion,
        } for t in tickets]

        return jsonify({
            "inventario_id": inventario_id,
            "nombre": inv.nombre,
            "codigo_interno": inv.codigo_interno,
            "historial_movimientos": movs,
            "historial_tickets": tks,
        }), 200
    except Exception as e:
        return manejar_error(e, "historial_aparato")


@inventario_bp.route('/importar', methods=['POST'], strict_slashes=False)
@jwt_required()
def importar_inventario():
    file = request.files.get('file')
    if not file:
        return jsonify({"message": "No se subió archivo"}), 400
    filename = secure_filename(file.filename)
    tmp_dir = tempfile.gettempdir()
    filepath = os.path.join(tmp_dir, filename)
    file.save(filepath)
    
    # Soporte para encoding flexible
    if filename.lower().endswith('.csv'):
        import chardet
        with open(filepath, 'rb') as f:
            encoding = chardet.detect(f.read())['encoding'] or 'utf-8'
        df = pd.read_csv(filepath, encoding=encoding)
    else:
        df = pd.read_excel(filepath)

    agregados, errores = 0, 0
    for idx, row in df.iterrows():
        try:
            # Ajusta estos campos a los de tu modelo de inventario
            inv = InventarioGeneral(
                nombre=str(row['nombre']).strip(),
                descripcion=str(row['descripcion']).strip(),
                tipo=str(row['tipo']).strip(),
                marca=str(row['marca']).strip(),
                proveedor=str(row['proveedor']).strip(),
                categoria=str(row['categoria']).strip(),
                unidad_medida=str(row['unidad_medida']).strip(),
                grupo_muscular=str(row['grupo_muscular']).strip(),
                codigo_interno=str(row['codigo_interno']).strip()
            )
            db.session.add(inv)
            agregados += 1
        except Exception as e:
            print(f"Error en fila {idx+2}: {e}")
            errores += 1
    db.session.commit()
    os.remove(filepath)
    return jsonify({"message": f"Importación exitosa. Agregados: {agregados}. Errores: {errores}"}), 200

@inventario_bp.route('/plantilla', methods=['GET'], strict_slashes=False)
@jwt_required()
def plantilla_inventario():
    # Ajusta los campos a tu modelo
    columnas = [
        "nombre", "descripcion", "tipo", "marca", "proveedor",
        "categoria", "unidad_medida", "grupo_muscular", "codigo_interno"
    ]
    # Fila de ejemplo (puedes poner más ejemplos o dejar en blanco)
    ejemplo = {
        "nombre": "Banca plana",
        "descripcion": "Banco plano",
        "tipo": "aparato",
        "marca": "Flex",
        "proveedor": "UltraGym",
        "categoria": "Maquinas",
        "unidad_medida": "pieza",
        "grupo_muscular": "Pecho",
        "codigo_interno": "01PLBPFL",
        "subcategoria": "Peso libre"
    }
    df = pd.DataFrame([ejemplo])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='plantilla_inventario.xlsx'
    )
    
    
@inventario_bp.route('/exportar', methods=['GET'], strict_slashes=False)
@jwt_required()
def exportar_inventario():
    registros = InventarioGeneral.query.all()
    # Extrae los campos igual que en la plantilla, agrega los que uses
    data = [
        {
            "nombre": r.nombre,
            "descripcion": r.descripcion,
            "tipo": r.tipo,
            "marca": r.marca,
            "proveedor": r.proveedor,
            "categoria": r.categoria,
            "unidad_medida": r.unidad_medida,
            "grupo_muscular": r.grupo_muscular,
            "codigo_interno": r.codigo_interno,
            "subcategoria": r.subcategoria, 
            
        }
        for r in registros
    ]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='inventario.xlsx'
    )


@inventario_bp.route('/categorias-inventario', methods=['GET'], strict_slashes=False)
@jwt_required()
def listar_categorias_inventario():
    try:
        parent_id = request.args.get('parent_id', type=int)
        nivel = request.args.get('nivel', type=int)
        nombre = (request.args.get('nombre') or '').strip()

        q = CategoriaInventario.query
        if parent_id is not None:
            q = q.filter(CategoriaInventario.parent_id == parent_id)
        if nivel is not None:
            q = q.filter(CategoriaInventario.nivel == nivel)
        if nombre:
            q = q.filter(CategoriaInventario.nombre.ilike(f'%{nombre}%'))

        rows = q.order_by(CategoriaInventario.nombre.asc()).all()
        data = [{'id': r.id, 'nombre': r.nombre, 'parent_id': r.parent_id, 'nivel': r.nivel} for r in rows]
        return jsonify(data), 200
    except Exception as e:
        return manejar_error(e, "listar_categorias_inventario")
