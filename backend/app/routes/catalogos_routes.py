# backend/app/routes/catalogos_routes.py

import io
import os
import tempfile

import pandas as pd
from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from rapidfuzz import fuzz
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.user_model import UserORM
from app.models.catalogos import (
    CatalogoClasificacion,
    CategoriaInventario,
    GrupoMuscular,
    Marca,
    Proveedor,
    TipoInventario,
    UnidadMedida,
)
from app.utils.error_handler import manejar_error

catalogos_bp = Blueprint("catalogos", __name__, url_prefix="/api/catalogos")


# ══════════════════════════════════════════════
# CONFIGURACIÓN GENERAL
# ══════════════════════════════════════════════

# Catálogos simples: se pueden manejar con el CRUD genérico.
# Las clasificaciones de tickets usan la misma tabla histórica, pero requieren
# validaciones propias por ser jerárquicas y estar ligadas a tickets.
CAT_MODELS = {
    "proveedores": Proveedor,
    "marcas": Marca,
    "unidades": UnidadMedida,
    "gruposmusculares": GrupoMuscular,
    "tipos": TipoInventario,
    "clasificaciones": CatalogoClasificacion,
    "categorias": CatalogoClasificacion,  # alias legacy usado por frontend de tickets
    "categorias_inventario": CategoriaInventario,
}

CLASIFICACION_KEYS = {"clasificaciones", "categorias"}
ADMIN_CATALOG_ROLES = {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}


# ══════════════════════════════════════════════
# RESPUESTA ESTÁNDAR Y HELPERS GENERALES
# ══════════════════════════════════════════════

def respuesta_ok(data=None, message=None, code=200):
    resp = {}
    if message:
        resp["message"] = message
    if data is not None:
        resp["data"] = data
    return jsonify(resp), code


def normalizar(texto):
    """Normaliza texto para comparaciones tolerantes a espacios y mayúsculas."""
    return (texto or "").strip().lower().replace(" ", "")


def normalizar_nombre_visible(texto):
    """Limpieza conservadora: no cambia acentos ni fuerza mayúsculas/minúsculas."""
    return " ".join((texto or "").strip().split())


def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "si", "sí"}


def catalogo_key(catalogo):
    return (catalogo or "").strip().lower()


def es_catalogo_clasificaciones(catalogo):
    return catalogo_key(catalogo) in CLASIFICACION_KEYS


def buscar_similares(model, nombre, umbral=80):
    """Busca posibles duplicados para catálogos simples.

    Para clasificaciones de tickets no usamos fuzzy universal, porque la regla
    correcta depende de departamento_id + parent_id.
    """
    nombre_norm = normalizar(nombre)
    existentes = [getattr(x, "nombre") for x in model.query.all()]
    return [x for x in existentes if fuzz.ratio(nombre_norm, normalizar(x)) >= umbral]


def _puede_administrar_catalogos():
    current_user_id = get_jwt_identity()
    user = UserORM.get_by_id(current_user_id)
    if not user:
        return False

    rol = (user.rol or "").strip().upper()
    return rol in ADMIN_CATALOG_ROLES


def _validar_admin_catalogos():
    """Centraliza permisos de escritura.

    El frontend puede ocultar menús, pero el backend es la fuente real de
    permisos. Lecturas se mantienen disponibles para los flujos de creación y
    consulta de tickets; escrituras quedan restringidas.
    """
    if not _puede_administrar_catalogos():
        return respuesta_ok(message="No tienes permiso para administrar catálogos.", code=403)
    return None


# ══════════════════════════════════════════════
# HELPERS ESPECÍFICOS: CLASIFICACIONES DE TICKETS
# ══════════════════════════════════════════════

def _clasificacion_to_dict(nodo, incluir_hijos=False, include_inactive=False):
    data = {
        "id": nodo.id,
        "nombre": nodo.nombre,
        "nivel": nodo.nivel,
        "parent_id": nodo.parent_id,
        "departamento_id": nodo.departamento_id,
        "activo": bool(getattr(nodo, "activo", True)),
    }

    if hasattr(nodo, "creado_en"):
        data["creado_en"] = nodo.creado_en.isoformat() if nodo.creado_en else None
    if hasattr(nodo, "actualizado_en"):
        data["actualizado_en"] = nodo.actualizado_en.isoformat() if nodo.actualizado_en else None

    if incluir_hijos:
        data["hijos"] = _build_clasificaciones_tree(nodo.id, nodo.departamento_id, include_inactive)

    return data


def _query_clasificaciones_base(include_inactive=False):
    query = CatalogoClasificacion.query
    if not include_inactive:
        query = query.filter(CatalogoClasificacion.activo.is_(True))
    return query


def _build_clasificaciones_tree(parent_id, departamento_id=None, include_inactive=False):
    query = _query_clasificaciones_base(include_inactive).filter(
        CatalogoClasificacion.parent_id == parent_id
    )

    if departamento_id:
        query = query.filter(CatalogoClasificacion.departamento_id == departamento_id)

    nodos = query.order_by(CatalogoClasificacion.nivel.asc(), CatalogoClasificacion.nombre.asc()).all()

    return [
        _clasificacion_to_dict(nodo, incluir_hijos=True, include_inactive=include_inactive)
        for nodo in nodos
    ]


def _obtener_parent_id(data):
    parent_id = data.get("parent_id")
    if parent_id in ("", 0, "0"):
        return None
    if parent_id is None:
        return None
    try:
        return int(parent_id)
    except (TypeError, ValueError):
        raise ValueError("parent_id debe ser numérico")


def _obtener_departamento_id(data):
    departamento_id = data.get("departamento_id")
    if departamento_id in (None, ""):
        return None
    try:
        return int(departamento_id)
    except (TypeError, ValueError):
        raise ValueError("departamento_id debe ser numérico")


def _existe_duplicado_clasificacion(nombre, departamento_id, parent_id, excluir_id=None):
    query = CatalogoClasificacion.query.filter(
        db.func.lower(db.func.trim(CatalogoClasificacion.nombre)) == normalizar_nombre_visible(nombre).lower(),
        CatalogoClasificacion.departamento_id == departamento_id,
    )

    if parent_id is None:
        query = query.filter(CatalogoClasificacion.parent_id.is_(None))
    else:
        query = query.filter(CatalogoClasificacion.parent_id == parent_id)

    if excluir_id is not None:
        query = query.filter(CatalogoClasificacion.id != excluir_id)

    return query.first() is not None


def _es_descendiente(posible_padre_id, nodo_id):
    """Evita ciclos si en una fase futura se permite mover nodos."""
    actual = CatalogoClasificacion.query.get(posible_padre_id)
    while actual:
        if actual.id == nodo_id:
            return True
        if not actual.parent_id:
            return False
        actual = CatalogoClasificacion.query.get(actual.parent_id)
    return False


def _resolver_contexto_clasificacion(data):
    """Resuelve parent/departamento/nivel para crear una clasificación.

    El frontend puede sugerir nivel, pero el backend lo calcula para evitar
    jerarquías inconsistentes por error humano o payload manipulado.
    """
    parent_id = _obtener_parent_id(data)
    departamento_id = _obtener_departamento_id(data)
    padre = None

    if parent_id is not None:
        padre = CatalogoClasificacion.query.get(parent_id)
        if not padre:
            return None, respuesta_ok(message="La clasificación padre no existe.", code=400)

        if getattr(padre, "activo", True) is False:
            return None, respuesta_ok(message="No puedes crear hijos dentro de una clasificación desactivada.", code=409)

        if departamento_id is not None and int(departamento_id) != int(padre.departamento_id):
            return None, respuesta_ok(
                message="La clasificación hija debe pertenecer al mismo departamento que su padre.",
                code=400,
            )

        departamento_id = padre.departamento_id
        nivel = int(padre.nivel or 1) + 1
    else:
        if departamento_id is None:
            return None, respuesta_ok(message="departamento_id es obligatorio para clasificaciones raíz.", code=400)
        nivel = 1

    return {
        "parent_id": parent_id,
        "departamento_id": departamento_id,
        "nivel": nivel,
    }, None


def _crear_clasificacion_desde_payload(data):
    nombre = normalizar_nombre_visible(data.get("nombre"))
    if not nombre:
        return respuesta_ok(message="El nombre es obligatorio", code=400)

    try:
        contexto, error = _resolver_contexto_clasificacion(data)
    except ValueError as exc:
        return respuesta_ok(message=str(exc), code=400)

    if error:
        return error

    if _existe_duplicado_clasificacion(
        nombre=nombre,
        departamento_id=contexto["departamento_id"],
        parent_id=contexto["parent_id"],
    ):
        return respuesta_ok(
            message="Ya existe una clasificación con ese nombre bajo el mismo padre/departamento.",
            code=409,
        )

    try:
        nuevo = CatalogoClasificacion(
            nombre=nombre,
            parent_id=contexto["parent_id"],
            departamento_id=contexto["departamento_id"],
            nivel=contexto["nivel"],
            activo=True,
        )
        db.session.add(nuevo)
        db.session.commit()
        return respuesta_ok(_clasificacion_to_dict(nuevo), message="Clasificación creada correctamente", code=201)
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "crear_clasificacion")


def _editar_clasificacion_desde_payload(elemento_id, data):
    elemento = CatalogoClasificacion.query.get(elemento_id)
    if not elemento:
        return respuesta_ok(message="Clasificación no encontrada", code=404)

    nombre = normalizar_nombre_visible(data.get("nombre", elemento.nombre))
    if not nombre:
        return respuesta_ok(message="El nombre es obligatorio", code=400)

    # MVP: editar nombre sí; mover ramas no. Mover parent/departamento implica
    # recalcular niveles de descendientes y revisar tickets ligados.
    try:
        parent_id_payload = _obtener_parent_id(data) if "parent_id" in data else elemento.parent_id
        depto_payload = _obtener_departamento_id(data) if "departamento_id" in data else elemento.departamento_id
    except ValueError as exc:
        return respuesta_ok(message=str(exc), code=400)

    if parent_id_payload != elemento.parent_id or int(depto_payload) != int(elemento.departamento_id):
        return respuesta_ok(
            message=(
                "Por seguridad, esta versión solo permite editar el nombre. "
                "Mover clasificaciones de padre/departamento requiere un flujo específico."
            ),
            code=409,
        )

    if _existe_duplicado_clasificacion(
        nombre=nombre,
        departamento_id=elemento.departamento_id,
        parent_id=elemento.parent_id,
        excluir_id=elemento.id,
    ):
        return respuesta_ok(
            message="Ya existe una clasificación con ese nombre bajo el mismo padre/departamento.",
            code=409,
        )

    try:
        elemento.nombre = nombre
        db.session.commit()
        return respuesta_ok(_clasificacion_to_dict(elemento), message="Clasificación actualizada correctamente")
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "editar_clasificacion")


# ══════════════════════════════════════════════
# GET UNIVERSAL
# ══════════════════════════════════════════════
@catalogos_bp.route("/<string:catalogo>", methods=["GET"], strict_slashes=False)
@jwt_required()
def listar_catalogo(catalogo):
    key = catalogo_key(catalogo)

    if key in CLASIFICACION_KEYS:
        return listar_clasificaciones_planas()

    model = CAT_MODELS.get(key)
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)

    query = model.query

    # Aplica filtros dinámicos por query params cuando existen en el modelo.
    for key_arg, value in request.args.items():
        if hasattr(model, key_arg) and value not in (None, ""):
            column = getattr(model, key_arg)
            try:
                if str(column.type) == "INTEGER":
                    value = int(value)
                elif str(column.type) == "BOOLEAN":
                    value = parse_bool(value)
            except Exception:
                pass
            query = query.filter(column == value)

    if hasattr(model, "activo") and not parse_bool(request.args.get("include_inactive"), default=False):
        query = query.filter(model.activo.is_(True))

    resultados = query.order_by(model.id.desc()).all()
    data = []
    for r in resultados:
        item = {"id": r.id, "nombre": r.nombre}
        for c in r.__table__.columns:
            if c.name not in ("id", "nombre"):
                item[c.name] = getattr(r, c.name)
        data.append(item)

    return respuesta_ok(data)


# ══════════════════════════════════════════════
# POST UNIVERSAL / CREACIÓN CONTROLADA
# ══════════════════════════════════════════════
@catalogos_bp.route("/<string:catalogo>", methods=["POST"], strict_slashes=False)
@jwt_required()
def crear_catalogo(catalogo):
    permiso_error = _validar_admin_catalogos()
    if permiso_error:
        return permiso_error

    key = catalogo_key(catalogo)
    data = request.get_json(silent=True) or {}

    if key in CLASIFICACION_KEYS:
        return _crear_clasificacion_desde_payload(data)

    model = CAT_MODELS.get(key)
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)

    nombre = normalizar_nombre_visible(data.get("nombre"))
    if not nombre:
        return respuesta_ok(message="El nombre es obligatorio", code=400)

    similares = buscar_similares(model, nombre, umbral=80)
    forzar = parse_bool(request.args.get("forzar"), default=False)
    if similares and not forzar:
        return respuesta_ok(
            {"similares": similares, "forzar": True},
            message=f"Posible duplicado detectado: {similares}",
            code=409,
        )

    campos = {}
    for c in model.__table__.columns:
        if c.name not in ("id", "nombre") and c.name in data:
            campos[c.name] = data[c.name]

    try:
        nuevo = model(nombre=nombre, **campos)
        db.session.add(nuevo)
        db.session.commit()
        return respuesta_ok({"id": nuevo.id}, message="Elemento creado correctamente", code=201)
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, f"crear_{catalogo}")


# ══════════════════════════════════════════════
# PUT UNIVERSAL / EDICIÓN CONTROLADA
# ══════════════════════════════════════════════
@catalogos_bp.route("/<string:catalogo>/<int:elemento_id>", methods=["PUT"], strict_slashes=False)
@jwt_required()
def editar_catalogo(catalogo, elemento_id):
    permiso_error = _validar_admin_catalogos()
    if permiso_error:
        return permiso_error

    key = catalogo_key(catalogo)
    data = request.get_json(silent=True) or {}

    if key in CLASIFICACION_KEYS:
        return _editar_clasificacion_desde_payload(elemento_id, data)

    model = CAT_MODELS.get(key)
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)

    elemento = model.query.get(elemento_id)
    if not elemento:
        return respuesta_ok(message="Elemento no encontrado", code=404)

    if "nombre" in data:
        nombre = normalizar_nombre_visible(data.get("nombre"))
        if not nombre:
            return respuesta_ok(message="El nombre es obligatorio", code=400)
        elemento.nombre = nombre

    for c in elemento.__table__.columns:
        if c.name not in ("id", "nombre") and c.name in data:
            setattr(elemento, c.name, data[c.name])

    try:
        db.session.commit()
        return respuesta_ok(message="Elemento actualizado")
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, f"editar_{catalogo}")


# ══════════════════════════════════════════════
# DELETE UNIVERSAL
# ══════════════════════════════════════════════
@catalogos_bp.route("/<string:catalogo>/<int:elemento_id>", methods=["DELETE"], strict_slashes=False)
@jwt_required()
def eliminar_catalogo(catalogo, elemento_id):
    permiso_error = _validar_admin_catalogos()
    if permiso_error:
        return permiso_error

    key = catalogo_key(catalogo)

    # Las clasificaciones de tickets no se borran físicamente: tienen histórico,
    # relación con tickets y jerarquía. El flujo correcto es desactivar/reactivar.
    if key in CLASIFICACION_KEYS:
        return respuesta_ok(
            message=(
                "No se permite eliminar físicamente clasificaciones de tickets. "
                "Usa desactivación para conservar histórico y evitar romper tickets existentes."
            ),
            code=409,
        )

    model = CAT_MODELS.get(key)
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)

    elemento = model.query.get(elemento_id)
    if not elemento:
        return respuesta_ok(message="Elemento no encontrado", code=404)

    try:
        db.session.delete(elemento)
        db.session.commit()
        return respuesta_ok(message="Elemento eliminado")
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, f"eliminar_{catalogo}")


# ══════════════════════════════════════════════
# ENDPOINTS ESPECÍFICOS: CLASIFICACIONES DE TICKETS
# ══════════════════════════════════════════════
@catalogos_bp.route("/clasificaciones/arbol", methods=["GET"], strict_slashes=False)
@jwt_required()
def arbol_clasificaciones():
    departamento_id = request.args.get("departamento_id", type=int)
    include_inactive = parse_bool(request.args.get("include_inactive"), default=False)

    try:
        if departamento_id:
            return respuesta_ok(_build_clasificaciones_tree(None, departamento_id, include_inactive))

        deptos_query = db.session.query(CatalogoClasificacion.departamento_id).distinct()
        if not include_inactive:
            deptos_query = deptos_query.filter(CatalogoClasificacion.activo.is_(True))

        arbol = []
        for (dep_id,) in deptos_query.order_by(CatalogoClasificacion.departamento_id.asc()).all():
            arbol.append({
                "departamento_id": dep_id,
                "arbol": _build_clasificaciones_tree(None, dep_id, include_inactive),
            })

        return respuesta_ok(arbol)
    except Exception as e:
        return manejar_error(e, "arbol_clasificaciones")


def listar_clasificaciones_planas():
    """Lista plana usada por selects encadenados y filtros.

    Por default devuelve solo activas para no ofrecer opciones desactivadas al
    crear tickets. El módulo administrativo puede pedir include_inactive=true.
    """
    include_inactive = parse_bool(request.args.get("include_inactive"), default=False)
    departamento_id = request.args.get("departamento_id", type=int)
    parent_id_raw = request.args.get("parent_id")

    query = _query_clasificaciones_base(include_inactive)

    if departamento_id:
        query = query.filter(CatalogoClasificacion.departamento_id == departamento_id)

    if parent_id_raw is not None:
        try:
            parent_id = int(parent_id_raw)
            query = query.filter(CatalogoClasificacion.parent_id == parent_id)
        except ValueError:
            return respuesta_ok(message="parent_id inválido", code=400)

    filas = query.order_by(
        CatalogoClasificacion.departamento_id.asc(),
        CatalogoClasificacion.nivel.asc(),
        CatalogoClasificacion.nombre.asc(),
    ).all()

    return respuesta_ok([_clasificacion_to_dict(fila) for fila in filas])


@catalogos_bp.route("/clasificaciones/<int:elemento_id>/desactivar", methods=["POST"], strict_slashes=False)
@jwt_required()
def desactivar_clasificacion(elemento_id):
    permiso_error = _validar_admin_catalogos()
    if permiso_error:
        return permiso_error

    elemento = CatalogoClasificacion.query.get(elemento_id)
    if not elemento:
        return respuesta_ok(message="Clasificación no encontrada", code=404)

    hijos_activos = CatalogoClasificacion.query.filter_by(parent_id=elemento.id, activo=True).count()
    if hijos_activos > 0:
        return respuesta_ok(
            message=(
                "No se puede desactivar esta clasificación porque tiene "
                "subclasificaciones activas. Desactiva primero sus hijos."
            ),
            code=409,
        )

    if elemento.activo is False:
        return respuesta_ok(_clasificacion_to_dict(elemento), message="La clasificación ya estaba desactivada")

    try:
        elemento.activo = False
        db.session.commit()
        return respuesta_ok(_clasificacion_to_dict(elemento), message="Clasificación desactivada correctamente")
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "desactivar_clasificacion")


@catalogos_bp.route("/clasificaciones/<int:elemento_id>/reactivar", methods=["POST"], strict_slashes=False)
@jwt_required()
def reactivar_clasificacion(elemento_id):
    permiso_error = _validar_admin_catalogos()
    if permiso_error:
        return permiso_error

    elemento = CatalogoClasificacion.query.get(elemento_id)
    if not elemento:
        return respuesta_ok(message="Clasificación no encontrada", code=404)

    if elemento.parent_id:
        padre = CatalogoClasificacion.query.get(elemento.parent_id)
        if not padre:
            return respuesta_ok(message="No se puede reactivar porque el padre ya no existe.", code=409)
        if padre.activo is False:
            return respuesta_ok(
                message="No se puede reactivar porque la clasificación padre está desactivada.",
                code=409,
            )

    if elemento.activo is True:
        return respuesta_ok(_clasificacion_to_dict(elemento), message="La clasificación ya estaba activa")

    if _existe_duplicado_clasificacion(
        nombre=elemento.nombre,
        departamento_id=elemento.departamento_id,
        parent_id=elemento.parent_id,
        excluir_id=elemento.id,
    ):
        return respuesta_ok(
            message="No se puede reactivar porque ya existe una clasificación equivalente.",
            code=409,
        )

    try:
        elemento.activo = True
        db.session.commit()
        return respuesta_ok(_clasificacion_to_dict(elemento), message="Clasificación reactivada correctamente")
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, "reactivar_clasificacion")


@catalogos_bp.route("/clasificaciones/todos", methods=["GET"], strict_slashes=False)
@jwt_required()
def todas_las_clasificaciones():
    # Endpoint legacy: se conserva para compatibilidad, pero ahora devuelve
    # estado activo para que el frontend pueda distinguir opciones desactivadas.
    include_inactive = parse_bool(request.args.get("include_inactive"), default=False)
    query = _query_clasificaciones_base(include_inactive)
    clasifs = query.order_by(CatalogoClasificacion.nombre.asc()).all()
    data = [_clasificacion_to_dict(c) for c in clasifs]
    return respuesta_ok(data)


# ══════════════════════════════════════════════
# BÚSQUEDA Y DROPDOWN
# ══════════════════════════════════════════════
@catalogos_bp.route("/<string:catalogo>/buscar", methods=["GET"], strict_slashes=False)
@jwt_required()
def buscar_catalogo(catalogo):
    key = catalogo_key(catalogo)
    model = CAT_MODELS.get(key)
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)

    termino = (request.args.get("q") or request.args.get("nombre") or "").strip()
    if not termino:
        return respuesta_ok([])

    query = model.query
    if hasattr(model, "activo") and not parse_bool(request.args.get("include_inactive"), default=False):
        query = query.filter(model.activo.is_(True))

    resultados = []
    for r in query.all():
        if fuzz.ratio(normalizar(termino), normalizar(r.nombre)) >= 70:
            item = {"id": r.id, "nombre": r.nombre}
            for c in r.__table__.columns:
                if c.name not in ("id", "nombre"):
                    item[c.name] = getattr(r, c.name)
            resultados.append(item)

    return respuesta_ok(resultados)


@catalogos_bp.route("/dropdown/<string:catalogo>", methods=["GET"], strict_slashes=False)
@jwt_required()
def dropdown_catalogo(catalogo):
    key = catalogo_key(catalogo)
    model = CAT_MODELS.get(key)
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)

    query = model.query
    if hasattr(model, "activo") and not parse_bool(request.args.get("include_inactive"), default=False):
        query = query.filter(model.activo.is_(True))

    data = [{"id": r.id, "label": r.nombre} for r in query.order_by(model.nombre).all()]
    return respuesta_ok(data)


# ══════════════════════════════════════════════
# IMPORT / EXPORT
# ══════════════════════════════════════════════
@catalogos_bp.route("/<string:catalogo>/importar", methods=["POST"], strict_slashes=False)
@jwt_required()
def importar_catalogo(catalogo):
    import re

    permiso_error = _validar_admin_catalogos()
    if permiso_error:
        return permiso_error

    key = catalogo_key(catalogo)

    # Importar árboles jerárquicos requiere un validador dedicado. El import
    # genérico puede crear nodos huérfanos, niveles erróneos o duplicados.
    if key in CLASIFICACION_KEYS:
        return respuesta_ok(
            message="La importación masiva de clasificaciones está deshabilitada hasta tener validación de árbol.",
            code=409,
        )

    model = CAT_MODELS.get(key)
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)

    if "file" not in request.files:
        return respuesta_ok(message="No se subió archivo", code=400)

    file = request.files["file"]
    filename = secure_filename(file.filename)
    tmp_dir = tempfile.gettempdir()
    filepath = os.path.join(tmp_dir, filename)
    file.save(filepath)

    try:
        if filename.lower().endswith(".csv"):
            import chardet
            with open(filepath, "rb") as f:
                result = chardet.detect(f.read())
                encoding = result["encoding"] or "utf-8"
            df = pd.read_csv(filepath, encoding=encoding)
        else:
            df = pd.read_excel(filepath)

        def limpiar_texto(texto):
            if pd.isna(texto):
                return ""
            texto = str(texto)
            texto = " ".join(texto.strip().split())
            texto = " ".join(w.capitalize() for w in texto.lower().split())
            texto = re.sub(r"[^\w áéíóúüñÁÉÍÓÚÜÑ]", "", texto)
            return texto

        agregados, ignorados, errores = 0, 0, 0
        for idx, row in df.iterrows():
            try:
                campos = {c: row[c] for c in row.index if c in model.__table__.columns.keys()}

                for key_campo in campos:
                    if isinstance(campos[key_campo], str):
                        campos[key_campo] = limpiar_texto(campos[key_campo])

                nombre = normalizar_nombre_visible(campos.get("nombre"))
                if not nombre:
                    errores += 1
                    continue

                existe = model.query.filter(
                    db.func.lower(db.func.trim(model.nombre)) == nombre.lower()
                ).first()

                if not existe:
                    campos["nombre"] = nombre
                    nuevo = model(**campos)
                    db.session.add(nuevo)
                    agregados += 1
                else:
                    ignorados += 1
            except Exception as e:
                errores += 1
                print(f"Error en la fila {idx + 2}: {e}, datos: {row}")

        db.session.commit()
        return respuesta_ok(
            message=(
                "Carga masiva exitosa. "
                f"Agregados: {agregados}, Duplicados ignorados: {ignorados}, Errores: {errores}"
            )
        )
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, f"importar_{catalogo}")
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@catalogos_bp.route("/<string:catalogo>/exportar", methods=["GET"], strict_slashes=False)
@jwt_required()
def exportar_catalogo(catalogo):
    key = catalogo_key(catalogo)
    model = CAT_MODELS.get(key)
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)

    query = model.query
    if hasattr(model, "activo") and not parse_bool(request.args.get("include_inactive"), default=True):
        query = query.filter(model.activo.is_(True))

    registros = query.all()
    data = [{c.name: getattr(r, c.name) for c in model.__table__.columns} for r in registros]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{catalogo}.xlsx",
    )


# ══════════════════════════════════════════════
# ENDPOINTS ESPECIALES: INVENTARIO
# ══════════════════════════════════════════════
@catalogos_bp.route("/inventario/categorias", methods=["GET"], strict_slashes=False)
@jwt_required()
def categorias_inventario_distintas():
    """Devuelve categorías oficiales de inventario, no clasificaciones de tickets."""
    try:
        filas = (
            db.session.query(CategoriaInventario)
            .filter(CategoriaInventario.activo.is_(True))
            .order_by(CategoriaInventario.nombre.asc())
            .all()
        )

        data = [
            {
                "id": fila.id,
                "nombre": (fila.nombre or "").strip(),
                "activo": bool(fila.activo),
            }
            for fila in filas
        ]
        return respuesta_ok(data)
    except Exception as e:
        return manejar_error(e, "categorias_inventario_listado")
