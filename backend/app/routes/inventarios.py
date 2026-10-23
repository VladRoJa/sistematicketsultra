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
from sqlalchemy import func, text as sa_text
from app. extensions import db
from app.models.catalogos import CategoriaInventario
from app.models.inventario import InventarioGeneral, MovimientoInventario, DetalleMovimiento, InventarioSucursal
from app.models.inventario_codigo_correccion import InventarioCodigoCorreccionORM
from app.models.pm_bitacora import PmBitacoraORM
from app.models.pm_preventivo import PmPreventivoConfigORM
from app.models.mantenimiento_equipo import FamiliaEquipoORM
from app.models.ticket_model import Ticket
from app.models.user_model import UserORM
from app.models.sucursal_model import Sucursal
from app.services.inventario_dashboard_service import consultar_resumen_inventario
from datetime import datetime, timezone
import pytz
from app.config import Config
from app. utils.error_handler import manejar_error
from app.models.sucursal_model import Sucursal
from app. utils.string_utils import normalizar_campo
from werkzeug.utils import secure_filename

inventario_bp = Blueprint('inventario', __name__, url_prefix='/api/inventario')

tz = pytz.timezone('America/Tijuana')


INVENTORY_ADMIN_ROLES = {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}
INVENTORY_GLOBAL_WRITE_ROLES = INVENTORY_ADMIN_ROLES | {"MANTENIMIENTO", "SISTEMAS", "TECNICO"}
INVENTORY_SCOPED_WRITE_ROLES = {"SR_MANTENIMIENTO", "AUX_MANTENIMIENTO"}


def _coerce_int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_required_int(value, field_name):
    parsed = _coerce_int_or_none(value)
    if parsed is None:
        return None, (
            jsonify({
                "error": "Payload inválido",
                "detail": f"{field_name} es requerido y debe ser entero",
            }),
            400,
        )
    return parsed, None


def _parse_positive_movement_quantity(value):
    """Acepta enteros positivos (JSON numérico o cadena decimal ASCII)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        cantidad = value
    elif isinstance(value, str) and value.strip().isascii() and value.strip().isdecimal():
        cantidad = int(value.strip())
    else:
        return None
    return cantidad if cantidad > 0 else None


def _get_current_user_id_required():
    user_id = _coerce_int_or_none(get_jwt_identity())
    if user_id is None:
        return None, (
            jsonify({
                "error": "Sesión inválida",
                "detail": "No se pudo resolver el usuario autenticado actual.",
            }),
            401,
        )
    return user_id, None


def _get_current_inventory_user():
    current_user_id = _coerce_int_or_none(get_jwt_identity())
    if current_user_id is None:
        return None

    return UserORM.get_by_id(current_user_id)


def _normalize_sucursales_ids(raw_value):
    if not isinstance(raw_value, list):
        return []

    normalized = []
    for item in raw_value:
        parsed = _coerce_int_or_none(item)
        if parsed is not None:
            normalized.append(parsed)

    return sorted(set(normalized))


def _get_user_sucursales_scope_from_db(user_id):
    rows = db.session.execute(
        db.text("SELECT sucursal_id FROM usuario_sucursal WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchall()
    return sorted({int(row[0]) for row in rows if row[0] is not None})





def _resolve_inventory_read_sucursal_ids(requested_sucursal_id=None):
    user = _get_current_inventory_user()
    requested_sucursal_id = _coerce_int_or_none(requested_sucursal_id)

    if not user:
        return None, (
            jsonify({
                "error": "Unauthorized",
                "detail": "Sesión inválida.",
            }),
            401,
        )

    rol = str(getattr(user, "rol", "") or "").strip().upper()

    if rol in INVENTORY_GLOBAL_WRITE_ROLES:
        if requested_sucursal_id is not None:
            return [requested_sucursal_id], None
        return None, None

    allowed_sucursales = []

    if rol == "SR_MANTENIMIENTO":
        allowed_sucursales = _normalize_sucursales_ids(
            getattr(user, "sucursales_ids", [])
        )

        if not allowed_sucursales:
            allowed_sucursales = _get_user_sucursales_scope_from_db(user.id)

    elif rol == "AUX_MANTENIMIENTO":
        user_sucursal_id = _coerce_int_or_none(getattr(user, "sucursal_id", None))
        if user_sucursal_id is not None:
            allowed_sucursales = [user_sucursal_id]

    else:
        user_sucursal_id = _coerce_int_or_none(getattr(user, "sucursal_id", None))
        if user_sucursal_id is not None:
            allowed_sucursales = [user_sucursal_id]

    allowed_sucursales = sorted(set(allowed_sucursales))

    if not allowed_sucursales:
        return None, (
            jsonify({
                "error": "Forbidden",
                "detail": "No tienes sucursales asignadas para consultar existencias.",
            }),
            403,
        )

    if requested_sucursal_id is not None:
        if requested_sucursal_id not in allowed_sucursales:
            return None, (
                jsonify({
                    "error": "Forbidden",
                    "detail": "No tienes acceso para consultar existencias de esta sucursal.",
                }),
                403,
            )

        return [requested_sucursal_id], None

    return allowed_sucursales, None


def _require_inventory_global_write():
    user = _get_current_inventory_user()
    rol = str(getattr(user, "rol", "") or "").strip().upper() if user else ""

    if rol in INVENTORY_GLOBAL_WRITE_ROLES:
        return None

    return jsonify({
        "error": "Forbidden",
        "detail": "No tienes permiso para administrar el inventario maestro.",
    }), 403


def _require_inventory_movement_write(sucursal_id):
    user = _get_current_inventory_user()
    target_sucursal_id = _coerce_int_or_none(sucursal_id)

    if not user:
        return jsonify({
            "error": "Unauthorized",
            "detail": "Sesión inválida.",
        }), 401

    if target_sucursal_id is None:
        return jsonify({
            "error": "Bad Request",
            "detail": "sucursal_id inválido.",
        }), 400

    rol = str(getattr(user, "rol", "") or "").strip().upper()

    if rol in INVENTORY_GLOBAL_WRITE_ROLES:
        return None

    if rol == "AUX_MANTENIMIENTO":
        user_sucursal_id = _coerce_int_or_none(getattr(user, "sucursal_id", None))
        if user_sucursal_id is not None and target_sucursal_id == user_sucursal_id:
            return None

        return jsonify({
            "error": "Forbidden",
            "detail": "No tienes acceso para modificar inventario de esta sucursal.",
        }), 403

    if rol == "SR_MANTENIMIENTO":
        allowed_sucursales = _normalize_sucursales_ids(
            getattr(user, "sucursales_ids", [])
        )

        if not allowed_sucursales:
            allowed_sucursales = _get_user_sucursales_scope_from_db(user.id)

        if target_sucursal_id in allowed_sucursales:
            return None

        return jsonify({
            "error": "Forbidden",
            "detail": "No tienes acceso para modificar inventario de esta sucursal.",
        }), 403

    return jsonify({
        "error": "Forbidden",
        "detail": "No tienes permiso para modificar movimientos de inventario.",
    }), 403

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


def _familia_equipo_actual_payload(inventario):
    familia = getattr(inventario, 'familia_equipo', None)
    return {
        'familia_equipo_id': getattr(inventario, 'familia_equipo_id', None),
        'familia_equipo': familia.to_dict() if familia else None,
    }



def _sucursales_visibles_por_inventario(inventario_ids, sucursales_ids=None):
    """Obtener nombres reales de sucursales en lote, según permisos de lectura.

    None significa acceso global; una lista limita explícitamente las sucursales.
    """
    ids = sorted(set(inventario_ids))
    if not ids or (sucursales_ids is not None and not sucursales_ids):
        return {}

    consulta = (
        db.session.query(InventarioSucursal.inventario_id, Sucursal.sucursal)
        .join(Sucursal, Sucursal.sucursal_id == InventarioSucursal.sucursal_id)
        .filter(InventarioSucursal.inventario_id.in_(ids))
    )
    if sucursales_ids is not None:
        consulta = consulta.filter(
            InventarioSucursal.sucursal_id.in_(sucursales_ids)
        )

    nombres = {}
    for inventario_id, nombre in consulta.all():
        if nombre and nombre.strip():
            nombres.setdefault(inventario_id, set()).add(nombre.strip())

    return {
        inventario_id: ', '.join(sorted(sucursales, key=str.casefold))
        for inventario_id, sucursales in nombres.items()
    }

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


def _validar_familia_equipo_activa(value, tipo_inventario):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None

    familia_id = _coerce_int_or_none(value)
    if familia_id is None or familia_id <= 0:
        return None, error_response('familia_equipo_id debe ser un entero positivo')

    if str(tipo_inventario or '').strip().lower() not in {'aparato', 'aparatos'}:
        return None, error_response('La familia de equipo sólo aplica a inventario de tipo aparato')

    familia = FamiliaEquipoORM.query.filter_by(
        id=familia_id,
        activo=True,
    ).first()
    if not familia:
        return None, error_response('Familia de equipo activa no encontrada')

    return familia.id, None


def _bloquear_escritura_codigos():
    """Serializa altas y correcciones de códigos mientras se sanea el legado.

    No sustituye una restricción UNIQUE en PostgreSQL: otras rutas de escritura
    deberán usar este mismo contrato hasta depurar duplicados históricos.
    """
    db.session.execute(
        sa_text("SELECT pg_advisory_xact_lock(:dominio, :operacion)"),
        {"dominio": 51022, "operacion": 11},
    )


# Crear un nuevo inventario (producto/aparato/unificado)
@inventario_bp.route('/', methods=['POST'], strict_slashes=False)
@jwt_required()
def crear_inventario():
    try:
        forbidden = _require_inventory_global_write()
        if forbidden:
            return forbidden

        data = request.get_json()
        if not data.get('nombre') or not data.get('categoria'):
            return error_response('Nombre y categoría son obligatorios')

        # Los equipos individualizados pueden compartir nombre y marca, pero
        # su código interno debe distinguirlos en TODO el catálogo.
        # Los duplicados históricos se preservan para revisión por separado.
        codigo = normalizar_campo(data.get('codigo_interno')).upper()
        tipo_inventario = normalizar_campo(data.get('tipo', 'producto'))
        tipo_normalizado = tipo_inventario.casefold()
        requiere_codigo = tipo_normalizado in {
            'aparato', 'aparatos', 'sistema', 'sistemas',
            'dispositivo', 'dispositivos',
        }

        if requiere_codigo and not codigo:
            return error_response('Código interno obligatorio para aparatos y dispositivos')

        if codigo:
            _bloquear_escritura_codigos()
            existe_codigo = InventarioGeneral.query.filter(
                func.upper(func.trim(InventarioGeneral.codigo_interno)) == codigo
            ).first()
            if existe_codigo:
                return error_response(
                    f'El código interno {codigo} ya está registrado', 409
                )
        else:
            # Productos genéricos sin código conservan la regla histórica.
            existe = InventarioGeneral.query.filter_by(
                nombre=data['nombre'].strip(),
                marca=(data.get('marca') or '').strip(),
            ).first()
            if existe:
                return error_response('Ya existe un producto con ese nombre y marca', 409)

        ahora = datetime.now(tz)
        # --- Validaciones numéricas ---
        try:
            gasto_sem = _parse_int_nonneg(data.get('gasto_sem'), 'gasto_sem')
            gasto_mes = _parse_int_nonneg(data.get('gasto_mes'), 'gasto_mes')
            pedido_mes = _parse_int_nonneg(data.get('pedido_mes'), 'pedido_mes')
        except ValueError as ve:
            return error_response(str(ve))

        familia_equipo_id, familia_error = _validar_familia_equipo_activa(
            data.get('familia_equipo_id'),
            tipo_inventario,
        )
        if familia_error:
            return familia_error
        
        
        nuevo = InventarioGeneral(
            tipo=tipo_inventario,
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
            subcategoria=normalizar_campo(data.get('subcategoria', '')),
            familia_equipo_id=familia_equipo_id,
            
        )


        db.session.add(nuevo)
        db.session.commit()
        return success_response('Producto creado correctamente', {'inventario_id': nuevo.id})

    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "crear_inventario")

# Obtener todo el inventario
# backend/app/routes/inventarios.py

@inventario_bp.route('/', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required()
def obtener_inventario():
    try:
        requested_sucursal_id = request.args.get('sucursal_id', type=int)
        allowed_sucursales, forbidden = _resolve_inventory_read_sucursal_ids(requested_sucursal_id)
        if forbidden:
            return forbidden

        sucursal_id = requested_sucursal_id
        categoria_inventario_id = request.args.get('categoria_inventario_id', type=int)

        def _resolver_categoria(inv):
            cat_id = getattr(inv, 'categoria_inventario_id', None)
            if cat_id:
                cat = CategoriaInventario.query.get(cat_id)
                if cat:
                    return (cat.nombre or ''), ''  # usamos solo catálogo
            return (inv.categoria or ''), (inv.subcategoria or '')

        # ---------- Con sucursal (JOIN) ----------
        if sucursal_id is not None or allowed_sucursales is not None:
            q = (db.session.query(InventarioGeneral, InventarioSucursal.stock)
                 .join(InventarioSucursal, InventarioSucursal.inventario_id == InventarioGeneral.id))

            if sucursal_id is not None:
                q = q.filter(InventarioSucursal.sucursal_id == sucursal_id)
            elif allowed_sucursales is not None:
                q = q.filter(InventarioSucursal.sucursal_id.in_(allowed_sucursales))
            if categoria_inventario_id is not None:
                q = q.filter(InventarioGeneral.categoria_inventario_id == categoria_inventario_id)
            # opcional: solo con stock
            # q = q.filter(InventarioSucursal.stock > 0)

            rows = q.order_by(InventarioGeneral.nombre.asc()).all()
            scope_sucursales = (
                [sucursal_id] if sucursal_id is not None else allowed_sucursales
            )
            sucursales_por_id = _sucursales_visibles_por_inventario(
                (inv.id for inv, _ in rows), scope_sucursales
            )
            data = []
            for inv, stock in rows:
                categoria_res, subcat_res = _resolver_categoria(inv)
                data.append({
                    'id': inv.id,
                    'tipo': inv.tipo,
                    'nombre': inv.nombre,
                    'sucursales': sucursales_por_id.get(inv.id, 'Sin asignación'),
                    'descripcion': inv.descripcion,
                    'marca': inv.marca,
                    'proveedor': inv.proveedor,
                    'categoria': categoria_res,
                    'subcategoria': subcat_res,
                    'unidad_medida': inv.unidad_medida,
                    'unidad_compra': inv.unidad_compra,
                    'factor_compra': inv.factor_compra,
                    'codigo_interno': inv.codigo_interno,
                    'no_equipo': inv.no_equipo,
                    'gasto_sem': inv.gasto_sem,
                    'gasto_mes': inv.gasto_mes,
                    'pedido_mes': inv.pedido_mes,
                    'semana_pedido': inv.semana_pedido,
                    'fecha_inventario': str(inv.fecha_inventario) if inv.fecha_inventario else None,
                    'grupo_muscular': inv.grupo_muscular,
                    'stock': stock,
                    'categoria_inventario_id': getattr(inv, 'categoria_inventario_id', None),
                    **_familia_equipo_actual_payload(inv),
                })
            return jsonify(data), 200

        # ---------- Global (sin sucursal) ----------
        q = InventarioGeneral.query
        if categoria_inventario_id is not None:
            q = q.filter(InventarioGeneral.categoria_inventario_id == categoria_inventario_id)

        invs = q.order_by(InventarioGeneral.nombre.asc()).all()
        sucursales_por_id = _sucursales_visibles_por_inventario(
            (inv.id for inv in invs)
        )
        data = []
        for inv in invs:
            categoria_res, subcat_res = _resolver_categoria(inv)
            data.append({
                'id': inv.id,
                'tipo': inv.tipo,
                'nombre': inv.nombre,
                'sucursales': sucursales_por_id.get(inv.id, 'Sin asignación'),
                'descripcion': inv.descripcion,
                'marca': inv.marca,
                'proveedor': inv.proveedor,
                'categoria': categoria_res,
                'subcategoria': subcat_res,
                'unidad_medida': inv.unidad_medida,
                'unidad_compra': inv.unidad_compra,
                'factor_compra': inv.factor_compra,
                'codigo_interno': inv.codigo_interno,
                'no_equipo': inv.no_equipo,
                'gasto_sem': inv.gasto_sem,
                'gasto_mes': inv.gasto_mes,
                'pedido_mes': inv.pedido_mes,
                'semana_pedido': inv.semana_pedido,
                'fecha_inventario': str(inv.fecha_inventario) if inv.fecha_inventario else None,
                'grupo_muscular': inv.grupo_muscular,
                'categoria_inventario_id': getattr(inv, 'categoria_inventario_id', None),
                **_familia_equipo_actual_payload(inv),
            })
        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "obtener_inventario")


# Registrar entrada/salida de inventario
@inventario_bp.route('/movimientos', methods=['POST'], strict_slashes=False)
@jwt_required()
def registrar_movimiento():
    try:
        data = request.get_json() or {}
        tipo = data.get('tipo_movimiento')

        sucursal_id, sucursal_error = _parse_required_int(data.get('sucursal_id'), 'sucursal_id')
        if sucursal_error:
            return sucursal_error

        usuario_id, usuario_error = _get_current_user_id_required()
        if usuario_error:
            return usuario_error

        forbidden = _require_inventory_movement_write(sucursal_id)
        if forbidden:
            return forbidden

        inventarios = data.get('inventarios', [])
        observaciones = data.get('observaciones', '')

        if tipo not in ['entrada', 'salida'] or not isinstance(inventarios, list) or not inventarios:
            return error_response('Datos inválidos')

        # Primero validar todo el payload, sin crear movimientos ni modificar stock.
        validados = []
        for indice, producto in enumerate(inventarios, start=1):
            if not isinstance(producto, dict):
                return error_response(f'Producto {indice}: formato inválido')
            cantidad = _parse_positive_movement_quantity(producto.get('cantidad'))
            if cantidad is None:
                return error_response(f'Producto {indice}: cantidad debe ser un entero positivo')
            inventario_id = _coerce_int_or_none(producto.get('inventario_id'))
            if inventario_id is None or inventario_id <= 0:
                return error_response(f'Producto {indice}: inventario_id inválido')
            validados.append((producto, inventario_id, cantidad))

        # FOR UPDATE sobre los artículos, en orden estable. Esto serializa
        # incluso la primera entrada cuando aún no existe InventarioSucursal.
        # Además protege contra carreras al crear el par (inventario, sucursal).
        inventarios_por_id = {}
        for inventario_id in sorted({item[1] for item in validados}):
            inv = (
                InventarioGeneral.query
                .filter_by(id=inventario_id)
                .with_for_update()
                .first()
            )
            if not inv:
                db.session.rollback()
                return error_response(f'Inventario {inventario_id} no existe')
            inventarios_por_id[inventario_id] = inv

        detalles_preparados = []
        totales_por_inventario = {}
        for producto, inventario_id, cantidad in validados:
            inv = inventarios_por_id[inventario_id]
            unidad_mov = normalizar_campo(producto.get('unidad_medida')) or inv.unidad_medida
            factor = 1
            if inv.unidad_compra and inv.factor_compra and inv.factor_compra > 1:
                if unidad_mov == normalizar_campo(inv.unidad_compra):
                    factor = inv.factor_compra

            cantidad_base = cantidad * factor
            detalles_preparados.append((inventario_id, cantidad_base, inv.unidad_medida))
            totales_por_inventario[inventario_id] = (
                totales_por_inventario.get(inventario_id, 0) + cantidad_base
            )

        # Bloquear todas las existencias antes de validar una sola salida.
        # Repeticiones de un mismo artículo se comprueban como una suma única.
        ajustes = []
        for inventario_id in sorted(totales_por_inventario):
            inventario_sucursal = (
                InventarioSucursal.query
                .filter_by(inventario_id=inventario_id, sucursal_id=sucursal_id)
                .with_for_update()
                .first()
            )
            nuevo = inventario_sucursal is None
            if nuevo:
                if tipo == 'salida':
                    db.session.rollback()
                    return error_response(
                        f'Stock insuficiente para el inventario {inventario_id}', 409
                    )
                inventario_sucursal = InventarioSucursal(
                    inventario_id=inventario_id,
                    sucursal_id=sucursal_id,
                    stock=0,
                )

            stock_actual = inventario_sucursal.stock
            if stock_actual is None or stock_actual < 0:
                db.session.rollback()
                return error_response(
                    f'Stock inválido para el inventario {inventario_id}', 409
                )
            cantidad_total = totales_por_inventario[inventario_id]
            if tipo == 'salida' and stock_actual < cantidad_total:
                db.session.rollback()
                return error_response(
                    f'Stock insuficiente para el inventario {inventario_id}', 409
                )
            stock_nuevo = (
                stock_actual + cantidad_total
                if tipo == 'entrada'
                else stock_actual - cantidad_total
            )
            ajustes.append((inventario_sucursal, stock_nuevo, nuevo))

        # Todas las validaciones ya pasaron. Persistir lote y stock en un commit.
        nuevo_movimiento = MovimientoInventario(
            tipo_movimiento=tipo,
            sucursal_id=sucursal_id,
            usuario_id=usuario_id,
            observaciones=observaciones,
            fecha=datetime.now(tz),
        )
        db.session.add(nuevo_movimiento)
        db.session.flush()

        for inventario_id, cantidad_base, unidad_medida in detalles_preparados:
            db.session.add(DetalleMovimiento(
                movimiento_id=nuevo_movimiento.id,
                inventario_id=inventario_id,
                cantidad=cantidad_base,
                unidad_medida=unidad_medida,
            ))

        for inventario_sucursal, stock_nuevo, nuevo in ajustes:
            inventario_sucursal.stock = stock_nuevo
            if nuevo:
                db.session.add(inventario_sucursal)

        db.session.commit()
        return success_response('Movimiento registrado correctamente', {'movimiento_id': nuevo_movimiento.id})

    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "registrar_movimiento")

# Ver historial de movimientos
@inventario_bp.route('/movimientos', methods=['GET'], strict_slashes=False)
@jwt_required()
def historial_movimientos():
    try:
        sucursal_id = request.args.get('sucursal_id', type=int)
        tipo = request.args.get('tipo_movimiento')

        allowed_sucursales, forbidden = _resolve_inventory_read_sucursal_ids(sucursal_id)
        if forbidden:
            return forbidden

        query = MovimientoInventario.query
        if allowed_sucursales is not None:
            query = query.filter(MovimientoInventario.sucursal_id.in_(allowed_sucursales))
        if sucursal_id is not None:
            query = query.filter(MovimientoInventario.sucursal_id == sucursal_id)
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
                'no_equipo': d.inventario.no_equipo,
                # Descriptores del catálogo ACTUAL: el historial debe poder
                # mostrarse aun antes de cargar GET /inventario/ en Angular.
                'nombre': d.inventario.nombre,
                'marca': d.inventario.marca,
                'proveedor': d.inventario.proveedor,
                'categoria': (
                    d.inventario.categoria_inventario.nombre
                    if d.inventario.categoria_inventario is not None
                    else d.inventario.categoria
                ),
            } for d in detalles]

            sucursal = Sucursal.query.get(m.sucursal_id)
            usuario = UserORM.query.get(m.usuario_id)
            actor_anulacion = (
                UserORM.query.get(m.anulado_por_usuario_id)
                if m.anulado_por_usuario_id is not None else None
            )

            resultado.append({
                'id': m.id,
                'tipo': m.tipo_movimiento,
                'fecha': m.fecha.strftime('%d/%m/%Y %H:%M'), 
                'usuario': usuario.username if usuario else "Desconocido",
                'usuario_id': m.usuario_id,
                'sucursal': sucursal.sucursal if sucursal else "Desconocida",  
                'sucursal_id': m.sucursal_id,
                'observaciones': m.observaciones,
                'anulado': m.anulado,
                'anulado_por_usuario_id': m.anulado_por_usuario_id,
                'usuario_anulacion': actor_anulacion.username if actor_anulacion else None,
                'anulado_en_utc': (
                    m.anulado_en_utc.isoformat() if m.anulado_en_utc else None
                ),
                'motivo_anulacion': m.motivo_anulacion,
                'inventarios': inventarios
            })

        return jsonify(resultado), 200

    except Exception as e:
        return manejar_error(e, "historial_movimientos")

# Reportes · Resumen para dashboard (únicamente agregados de lectura).
@inventario_bp.route('/reportes/resumen', methods=['GET'], strict_slashes=False)
@jwt_required()
def resumen_dashboard_inventario():
    try:
        raw_sucursal = request.args.get('sucursal_id')
        sucursal_id = None
        if raw_sucursal is not None:
            sucursal_id = _coerce_int_or_none(raw_sucursal)
            if sucursal_id is None or sucursal_id <= 0:
                return error_response('sucursal_id debe ser un entero positivo')

        raw_dias = request.args.get('periodo_dias', '30')
        periodo_dias = _coerce_int_or_none(raw_dias)
        if periodo_dias not in (7, 30, 90):
            return error_response('periodo_dias debe ser 7, 30 o 90')

        ids_autorizados, forbidden = _resolve_inventory_read_sucursal_ids(
            sucursal_id
        )
        if forbidden:
            return forbidden

        if sucursal_id is not None:
            sucursal_existente = db.session.query(
                Sucursal.sucursal_id
            ).filter(
                Sucursal.sucursal_id == sucursal_id
            ).first()
            if sucursal_existente is None:
                return error_response('Sucursal no encontrada', 404)

        return jsonify(consultar_resumen_inventario(
            sucursal_id=sucursal_id,
            ids_autorizados=ids_autorizados,
            periodo_dias=periodo_dias,
        )), 200
    except Exception as exc:
        return manejar_error(exc, 'resumen_dashboard_inventario')


# Ver existencias globales
@inventario_bp.route('/existencias', methods=['GET'], strict_slashes=False)
@jwt_required()
def ver_existencias():
    try:
        requested_sucursal_id = request.args.get('sucursal_id', type=int)
        allowed_sucursales, forbidden = _resolve_inventory_read_sucursal_ids(requested_sucursal_id)
        if forbidden:
            return forbidden

        def descripcion_larga(inv):
            partes = [
                inv.nombre,
                inv.marca,
                inv.proveedor,
                inv.categoria,
                f"ID:{inv.id}"
            ]
            return " - ".join([str(p) for p in partes if p])

        query = InventarioSucursal.query

        if allowed_sucursales is not None:
            query = query.filter(InventarioSucursal.sucursal_id.in_(allowed_sucursales))

        inventario = query.all()
        data = []

        for item in inventario:
            inventario_general = InventarioGeneral.query.get(item.inventario_id)
            sucursal = Sucursal.query.get(item.sucursal_id)

            data.append({
                'inventario_id': item.inventario_id,
                'nombre': inventario_general.nombre if inventario_general else 'Desconocido',
                'codigo_interno': inventario_general.codigo_interno if inventario_general else None,
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

# Listar sucursales (filtradas por rol/token del usuario autenticado)
@inventario_bp.route('/sucursales', methods=['GET'], strict_slashes=False)
@jwt_required()

def listar_sucursales():
    try:
        user = _get_current_inventory_user()
        if not user:
            return jsonify({
                "error": "Unauthorized",
                "detail": "Sesión inválida.",
            }), 401

        rol = str(getattr(user, "rol", "") or "").strip().upper()

        def is_admin(r: str) -> bool:
            return r in {"ADMINISTRADOR", "SUPER_ADMIN", "ADMIN"}

        def is_sistemas_full(r: str) -> bool:
            return r in {"SISTEMAS", "TECNICO"}

        def is_mantenimiento_full(r: str) -> bool:
            return r == "MANTENIMIENTO"

        def is_aux_mant(r: str) -> bool:
            return r == "AUX_MANTENIMIENTO" or r.startswith("AUX_MANT")

        def is_sr_mant(r: str) -> bool:
            return r == "SR_MANTENIMIENTO" or r.startswith("SR_MANT")

        def is_sistemas_scope(r: str) -> bool:
            return r in {"SISTEMAS", "TECNICO"}

        # 1) Admin / Mantenimiento global / Sistemas full => todas
        if is_admin(rol) or is_mantenimiento_full(rol) or is_sistemas_full(rol):
            sucursales = Sucursal.query.all()

        # 2) AUX => solo su sucursal_id desde DB
        elif is_aux_mant(rol):
            user_sucursal = _coerce_int_or_none(getattr(user, "sucursal_id", None))
            sucursales = (
                Sucursal.query.filter_by(sucursal_id=user_sucursal).all()
                if user_sucursal
                else []
            )

        # 3) SR_MANTENIMIENTO / roles scoped => sucursales asignadas desde DB
        else:
            allowed = _normalize_sucursales_ids(
                getattr(user, "sucursales_ids", [])
            )

            if not allowed and (is_sr_mant(rol) or is_sistemas_scope(rol)):
                allowed = _get_user_sucursales_scope_from_db(user.id)

            sucursales = (
                Sucursal.query.filter(Sucursal.sucursal_id.in_(allowed)).all()
                if allowed
                else []
            )

        data = [
            {"sucursal_id": s.sucursal_id, "sucursal": s.sucursal}
            for s in sucursales
        ]
        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "listar_sucursales")

# Editar inventario general
@inventario_bp.route('/<int:inventario_id>', methods=['PUT'], strict_slashes=False)
@jwt_required()
def editar_inventario(inventario_id):
    try:
        forbidden = _require_inventory_global_write()
        if forbidden:
            return forbidden

        inventario = InventarioGeneral.query.get(inventario_id)
        if not inventario:
            return error_response('Inventario no encontrado', 404)

        data = request.get_json()
        # El código interno solo se cambia por el flujo con historial obligatorio.
        if 'codigo_interno' in data:
            actual = str(inventario.codigo_interno or '').strip().upper()
            propuesto = normalizar_campo(data['codigo_interno']).upper()
            if actual != propuesto:
                return error_response(
                    'Para cambiar el código interno utiliza la corrección auditada',
                    409,
                )

        if 'familia_equipo_id' in data:
            tipo_inventario = data.get('tipo', inventario.tipo)
            familia_equipo_id, familia_error = _validar_familia_equipo_activa(
                data.get('familia_equipo_id'),
                tipo_inventario,
            )
            if familia_error:
                return familia_error
            inventario.familia_equipo_id = familia_equipo_id

        campos = [
            'tipo', 'nombre', 'descripcion', 'marca', 'proveedor',
            'categoria', 'unidad_medida',
            'no_equipo', 'gasto_sem', 'gasto_mes',
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

# Corrección trazable del identificador físico, sin alterar existencias.
@inventario_bp.route(
    '/<int:inventario_id>/corregir-codigo', methods=['POST'], strict_slashes=False
)
@jwt_required()
def corregir_codigo_interno(inventario_id):
    try:
        forbidden = _require_inventory_global_write()
        if forbidden:
            return forbidden

        actor_id, actor_error = _get_current_user_id_required()
        if actor_error:
            return actor_error

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return error_response('Formato JSON inválido')

        anterior_esperado = str(data.get('codigo_anterior') or '').strip().upper()
        nuevo = normalizar_campo(data.get('codigo_nuevo')).upper()
        motivo = str(data.get('motivo') or '').strip()
        if not anterior_esperado or not nuevo:
            return error_response('Código anterior y nuevo son obligatorios')
        if len(nuevo) > 50:
            return error_response('Código interno demasiado largo')
        if not 10 <= len(motivo) <= 500:
            return error_response('El motivo debe tener entre 10 y 500 caracteres')

        # Serializar contra las demás correcciones y altas del catálogo.
        _bloquear_escritura_codigos()
        inventario = (
            InventarioGeneral.query.filter_by(id=inventario_id)
            .with_for_update()
            .first()
        )
        if not inventario:
            db.session.rollback()
            return error_response('Inventario no encontrado', 404)

        actual = str(inventario.codigo_interno or '').strip().upper()
        if actual != anterior_esperado:
            db.session.rollback()
            return error_response(
                'El código cambió desde que abriste el formulario; actualiza la pantalla',
                409,
            )
        if actual == nuevo:
            db.session.rollback()
            return error_response('El código nuevo debe ser diferente al anterior')

        existe = InventarioGeneral.query.filter(
            func.upper(func.trim(InventarioGeneral.codigo_interno)) == nuevo,
            InventarioGeneral.id != inventario_id,
        ).first()
        if existe:
            db.session.rollback()
            return error_response('El código propuesto ya está registrado', 409)

        auditoria = InventarioCodigoCorreccionORM(
            inventario_id=inventario.id,
            actor_usuario_id=actor_id,
            codigo_anterior=actual,
            codigo_nuevo=nuevo,
            motivo=motivo,
        )
        inventario.codigo_interno = nuevo
        db.session.add(auditoria)
        # Un único commit: si falla el historial, también se revierte el cambio.
        db.session.commit()
        return success_response('Código interno corregido correctamente', {
            'inventario_id': inventario.id,
            'codigo_anterior': actual,
            'codigo_nuevo': nuevo,
        })
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, 'corregir_codigo_interno')


@inventario_bp.route(
    '/<int:inventario_id>/historial-codigos', methods=['GET'], strict_slashes=False
)
@jwt_required()
def historial_codigos_internos(inventario_id):
    try:
        forbidden = _require_inventory_global_write()
        if forbidden:
            return forbidden
        historial = (
            InventarioCodigoCorreccionORM.query
            .filter_by(inventario_id=inventario_id)
            .order_by(InventarioCodigoCorreccionORM.ocurrido_en_utc.desc())
            .all()
        )
        return jsonify([{
            'id': evento.id,
            'usuario_id': evento.actor_usuario_id,
            'codigo_anterior': evento.codigo_anterior,
            'codigo_nuevo': evento.codigo_nuevo,
            'motivo': evento.motivo,
            'ocurrido_en_utc': evento.ocurrido_en_utc.isoformat(),
        } for evento in historial]), 200
    except Exception as e:
        return manejar_error(e, 'historial_codigos_internos')


# Eliminar inventario general
@inventario_bp.route('/<int:inventario_id>', methods=['DELETE'], strict_slashes=False)
@jwt_required()
def eliminar_inventario(inventario_id):
    try:
        forbidden = _require_inventory_global_write()
        if forbidden:
            return forbidden

        # Bloquear el artículo mientras comprobamos sus relaciones, para
        # impedir nuevas referencias concurrentes durante esta transacción.
        inventario = (
            InventarioGeneral.query
            .filter_by(id=inventario_id)
            .with_for_update()
            .first()
        )
        if not inventario:
            return error_response('Inventario no encontrado', 404)

        def conflicto(mensaje):
            db.session.rollback()
            return error_response(mensaje, 409)

        # No borrar un artículo que otros módulos siguen utilizando.
        if DetalleMovimiento.query.filter_by(inventario_id=inventario_id).first():
            return conflicto('No se puede eliminar: el inventario tiene movimientos registrados')

        # Una asignación de sucursal también bloquea el borrado con stock 0.
        if InventarioSucursal.query.filter_by(inventario_id=inventario_id).first():
            return conflicto('No se puede eliminar: el inventario está asignado a sucursales')

        if Ticket.query.filter_by(aparato_id=inventario_id).first():
            return conflicto('No se puede eliminar: el inventario está asociado a tickets')

        # Ambas relaciones de PM usan ON DELETE CASCADE: proteger su historial.
        if PmBitacoraORM.query.filter_by(inventario_id=inventario_id).first():
            return conflicto('No se puede eliminar: el inventario tiene bitácoras de mantenimiento')

        if PmPreventivoConfigORM.query.filter_by(inventario_id=inventario_id).first():
            return conflicto('No se puede eliminar: el inventario tiene programación preventiva')

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
            'fecha_inventario': str(i.fecha_inventario) if i.fecha_inventario else None,
            **_familia_equipo_actual_payload(i),
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
            'fecha_inventario': str(i.fecha_inventario) if i.fecha_inventario else None,
            **_familia_equipo_actual_payload(i),
        } for i in inventario]
        return jsonify(data), 200

    except Exception as e:
        return manejar_error(e, "buscar_inventario")
    
    
@inventario_bp.route('/movimientos/<int:id>', methods=['DELETE'], strict_slashes=False)
@jwt_required()
def eliminar_movimiento(id):
    """No permitir jamás la ruta legacy que borraba historial físicamente."""
    return jsonify({
        "error": "El borrado definitivo de movimientos está deshabilitado.",
        "detail": "Utiliza POST /api/inventario/movimientos/<id>/anular con motivo obligatorio.",
    }), 405


@inventario_bp.route('/movimientos/<int:id>/anular', methods=['POST'], strict_slashes=False)
@jwt_required()
def anular_movimiento(id):
    """Revertir existencias y registrar autor/motivo en una única transacción."""
    try:
        data = request.get_json(silent=True) or {}
        motivo = data.get('motivo')
        if not isinstance(motivo, str) or not 10 <= len(motivo.strip()) <= 1000:
            return error_response(
                'El motivo de anulación debe contener entre 10 y 1000 caracteres.'
            )
        motivo = motivo.strip()

        actor_id, error_actor = _get_current_user_id_required()
        if error_actor:
            return error_actor

        # El bloqueo serializa la anulación: dos solicitudes no pueden revertir dos veces.
        mov = MovimientoInventario.query.filter_by(id=id).with_for_update().first()
        if not mov:
            return error_response('Movimiento no encontrado', 404)

        forbidden = _require_inventory_movement_write(mov.sucursal_id)
        if forbidden:
            db.session.rollback()
            return forbidden

        def conflicto(mensaje):
            db.session.rollback()
            return error_response(mensaje, 409)

        if mov.anulado:
            return conflicto('El movimiento ya está anulado. No puede revertirse dos veces.')

        detalles = list(mov.detalles)
        if not detalles or mov.tipo_movimiento not in ('entrada', 'salida'):
            return conflicto('El movimiento no tiene detalles válidos para revertir.')

        cantidades_por_inventario = {}
        for det in detalles:
            if not isinstance(det.cantidad, int) or det.cantidad <= 0:
                return conflicto(
                    f'Cantidad histórica inválida para el inventario {det.inventario_id}'
                )
            cantidades_por_inventario[det.inventario_id] = (
                cantidades_por_inventario.get(det.inventario_id, 0) + det.cantidad
            )

        ajustes = []
        for inventario_id in sorted(cantidades_por_inventario):
            fila = (
                InventarioSucursal.query
                .filter_by(inventario_id=inventario_id, sucursal_id=mov.sucursal_id)
                .with_for_update()
                .first()
            )
            if fila is None or fila.stock is None or fila.stock < 0:
                return conflicto(f'No se encontró stock válido para el inventario {inventario_id}')

            cantidad = cantidades_por_inventario[inventario_id]
            if mov.tipo_movimiento == 'entrada' and fila.stock < cantidad:
                return conflicto(
                    f'No se puede anular la entrada del inventario {inventario_id}: '
                    'las existencias actuales son insuficientes para revertirla.'
                )

            nuevo_stock = (
                fila.stock - cantidad if mov.tipo_movimiento == 'entrada'
                else fila.stock + cantidad
            )
            ajustes.append((fila, nuevo_stock))

        # Una sola confirmación conserva íntegros movimiento y detalles.
        for fila, nuevo_stock in ajustes:
            fila.stock = nuevo_stock

        mov.anulado = True
        mov.anulado_por_usuario_id = actor_id
        mov.anulado_en_utc = datetime.now(timezone.utc)
        mov.motivo_anulacion = motivo

        db.session.commit()
        return jsonify({
            "mensaje": "Movimiento anulado correctamente; historial conservado.",
            "movimiento_id": mov.id,
            "anulado": True,
        }), 200
    except Exception as exc:
        db.session.rollback()
        return manejar_error(exc, 'anular_movimiento')


@inventario_bp.route('/equipos', methods=['GET'], strict_slashes=False)
@jwt_required()

def listar_equipos():
    try:
        user = _get_current_inventory_user()
        if not user:
            return error_response("Usuario no encontrado", 404)

        rol = str(getattr(user, "rol", "") or "").strip().upper()
        department_id = _coerce_int_or_none(getattr(user, "department_id", None))
        is_admin = rol in {"ADMINISTRADOR", "SUPER_ADMIN", "ADMIN"}

        # ----------------------------
        # Tipo + enforcement por dept
        # ----------------------------
        tipo = (request.args.get("tipo") or "").strip().lower()

        DEP_MANTENIMIENTO = 1
        DEP_SISTEMAS = 7

        if not is_admin:
            if department_id == DEP_MANTENIMIENTO:
                tipo = "aparatos"
            elif department_id == DEP_SISTEMAS:
                tipo = "dispositivos"

        # Mapea valores recibidos a lo que existe en la base
        if tipo in ["aparato", "aparatos"]:
            tipo = "aparatos"
        elif tipo in ["sistema", "sistemas", "dispositivo", "dispositivos"]:
            tipo = "dispositivos"
        else:
            tipo = ""

        # ----------------------------
        # Sucursal scoped por rol
        # ----------------------------
        sucursal_id = request.args.get("sucursal_id", type=int)

        allowed_sucursales = _normalize_sucursales_ids(
            getattr(user, "sucursales_ids", [])
        )

        if rol == "SR_MANTENIMIENTO" and not allowed_sucursales:
            allowed_sucursales = _get_user_sucursales_scope_from_db(user.id)

        target_sucursal = sucursal_id or _coerce_int_or_none(
            getattr(user, "sucursal_id", None)
        )

        # ----------------------------
        # Query base
        # ----------------------------
        query = InventarioGeneral.query
        query = query.filter(InventarioGeneral.codigo_interno.isnot(None))

        if tipo:
            query = query.filter(db.func.lower(InventarioGeneral.tipo) == tipo)

        # ----------------------------
        # Filtro sucursal
        # ----------------------------
        # Reglas conservadas:
        # - Admin: puede la sucursal que mande o su sucursal default.
        # - MANTENIMIENTO / SISTEMAS / TECNICO: acceso full según comportamiento actual.
        # - SR_MANTENIMIENTO: solo sucursales asignadas.
        # - AUX_MANTENIMIENTO: solo user.sucursal_id.
        if is_admin or rol in {"MANTENIMIENTO", "SISTEMAS", "TECNICO"}:
            if target_sucursal:
                query = query.join(
                    InventarioSucursal,
                    InventarioSucursal.inventario_id == InventarioGeneral.id,
                ).filter(InventarioSucursal.sucursal_id == target_sucursal)

        elif rol == "AUX_MANTENIMIENTO":
            user_sucursal_id = _coerce_int_or_none(getattr(user, "sucursal_id", None))
            if not user_sucursal_id:
                return jsonify({
                    "error": "Forbidden",
                    "detail": "No tienes sucursal asignada.",
                }), 403

            query = query.join(
                InventarioSucursal,
                InventarioSucursal.inventario_id == InventarioGeneral.id,
            ).filter(InventarioSucursal.sucursal_id == user_sucursal_id)

        else:
            if target_sucursal not in allowed_sucursales:
                return jsonify({
                    "error": "Forbidden",
                    "detail": "No tienes acceso a esta sucursal",
                }), 403

            query = query.join(
                InventarioSucursal,
                InventarioSucursal.inventario_id == InventarioGeneral.id,
            ).filter(InventarioSucursal.sucursal_id == target_sucursal)

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
                **_familia_equipo_actual_payload(eq),
                "sucursal_ids": [
                    inv.sucursal_id for inv in eq.inventarios_sucursal
                ],
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


@inventario_bp.route('/por-categoria', methods=['GET'], strict_slashes=False)
@jwt_required()
def inventario_por_categoria():
    try:
        cat_inv_id = request.args.get('categoria_inventario_id', type=int)
        sucursal_id = request.args.get('sucursal_id', type=int)
        if not cat_inv_id:
            return error_response('categoria_inventario_id es requerido', 400)

        q = (db.session.query(InventarioGeneral)
             .filter(InventarioGeneral.categoria_inventario_id == cat_inv_id))

        if sucursal_id is not None:
            q = (q.join(InventarioSucursal, InventarioSucursal.inventario_id == InventarioGeneral.id)
                   .filter(InventarioSucursal.sucursal_id == sucursal_id))

        # ✅ En Postgres, el ORDER BY debe comenzar por la(s) columna(s) del DISTINCT ON
        q = q.order_by(InventarioGeneral.id.asc(), InventarioGeneral.nombre.asc())

        items = q.distinct(InventarioGeneral.id).all()

        return jsonify([
            {
                'id': i.id,
                'nombre': i.nombre,
                'marca': i.marca,
                'codigo_interno': i.codigo_interno,
            } for i in items
        ]), 200
    except Exception as e:
        return manejar_error(e, "inventario_por_categoria")



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

        allowed_sucursales, forbidden = _resolve_inventory_read_sucursal_ids(sucursal_id)
        if forbidden:
            return forbidden

        query = InventarioGeneral.query

        if tipo:
            query = query.filter(InventarioGeneral.tipo.ilike(f'%{tipo}%'))

        # Si se consulta una sucursal específica, ya fue validada contra el scope.
        # Si no se manda sucursal y el usuario no es global, se filtra por sus sucursales permitidas.
        scoped_sucursales = [sucursal_id] if sucursal_id else allowed_sucursales

        if scoped_sucursales is not None:
            ids_en_sucursal = [
                inv.inventario_id
                for inv in (
                    InventarioSucursal.query
                    .filter(InventarioSucursal.sucursal_id.in_(scoped_sucursales))
                    .filter(InventarioSucursal.stock > 0)
                    .all()
                )
            ]
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
            **_familia_equipo_actual_payload(i),
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
    forbidden = _require_inventory_global_write()
    if forbidden:
        return forbidden

    file = request.files.get('file')
    if not file or not file.filename:
        return error_response('No se subió archivo', 400)

    extension = os.path.splitext(secure_filename(file.filename))[1].lower()
    if extension not in {'.csv', '.xlsx'}:
        return error_response('Formato no permitido: utiliza CSV o XLSX', 400)

    # Leer el contenido en memoria: nunca escribir uploads en rutas temporales
    # compartidas bajo el nombre proporcionado por el cliente.
    max_bytes = 10 * 1024 * 1024
    contenido = file.read(max_bytes + 1)
    if not contenido:
        return error_response('El archivo está vacío', 400)
    if len(contenido) > max_bytes:
        return error_response('El archivo excede el límite de 10 MB', 413)

    try:
        if extension == '.csv':
            import chardet
            encoding = chardet.detect(contenido).get('encoding') or 'utf-8-sig'
            df = pd.read_csv(BytesIO(contenido), encoding=encoding, dtype=str)
        else:
            df = pd.read_excel(BytesIO(contenido), dtype=str)
    except Exception:
        return error_response('No se pudo leer el archivo CSV o XLSX', 400)

    if df.empty:
        return error_response('El archivo no contiene artículos', 400)

    df.columns = [str(col).strip().lower() for col in df.columns]
    if len(set(df.columns)) != len(df.columns):
        return error_response('El archivo contiene columnas duplicadas', 400)

    requeridas = {'nombre', 'tipo', 'categoria'}
    faltantes = sorted(requeridas - set(df.columns))
    if faltantes:
        return error_response('Faltan columnas obligatorias: ' + ', '.join(faltantes), 400)

    campos = (
        'nombre', 'descripcion', 'tipo', 'marca', 'proveedor',
        'categoria', 'unidad_medida', 'grupo_muscular', 'codigo_interno',
    )
    max_longitud = {
        'nombre': 255, 'tipo': 20, 'marca': 100, 'proveedor': 255,
        'categoria': 100, 'unidad_medida': 50,
        'grupo_muscular': 100, 'codigo_interno': 50,
    }

    def texto(valor):
        return '' if pd.isna(valor) else str(valor).strip()

    filas = []
    errores = []
    claves_archivo = set()
    # Validar todo el archivo antes de insertar siquiera un registro.
    for indice, row in df.iterrows():
        valores = {campo: texto(row.get(campo)) for campo in campos}
        fila_numero = indice + 2
        vacios = [campo for campo in requeridas if not valores[campo]]
        largos = [
            campo for campo, maximo in max_longitud.items()
            if len(valores[campo]) > maximo
        ]
        clave = (valores['nombre'], valores['marca'])

        if vacios:
            errores.append(f"Fila {fila_numero}: faltan {', '.join(sorted(vacios))}")
        elif largos:
            errores.append(f"Fila {fila_numero}: longitud excedida en {', '.join(largos)}")
        elif clave in claves_archivo:
            errores.append(f"Fila {fila_numero}: nombre y marca duplicados en el archivo")
        else:
            claves_archivo.add(clave)
            filas.append(valores)

    if errores:
        return jsonify({
            'error': 'Archivo inválido: no se importó ningún artículo',
            'detail': '; '.join(errores[:5]),
            'errores_total': len(errores),
        }), 400

    try:
        # Aplicar el mismo criterio de duplicidad que crear_inventario.
        existentes = {
            (nombre or '', marca or '')
            for nombre, marca in db.session.query(
                InventarioGeneral.nombre, InventarioGeneral.marca
            ).all()
        }
        duplicados = [
            fila['nombre'] for fila in filas
            if (fila['nombre'], fila['marca']) in existentes
        ]
        if duplicados:
            db.session.rollback()
            return jsonify({
                'error': 'El catálogo ya contiene artículos con el mismo nombre y marca',
                'detail': ', '.join(duplicados[:5]),
                'duplicados_total': len(duplicados),
            }), 409

        db.session.add_all([InventarioGeneral(**fila) for fila in filas])
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, 'importar_inventario')

    return jsonify({
        'message': f'Importación exitosa. Agregados: {len(filas)}. Errores: 0',
        'agregados': len(filas),
        'errores': 0,
    }), 200

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
    forbidden = _require_inventory_global_write()
    if forbidden:
        return forbidden

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
