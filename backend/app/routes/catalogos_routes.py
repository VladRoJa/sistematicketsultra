import io
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
import pandas as pd
from app. extensions import db
from app.models.catalogos import (
    CatalogoClasificacion, Proveedor, Marca, UnidadMedida, GrupoMuscular, TipoInventario
)
from app. utils.error_handler import manejar_error
from rapidfuzz import fuzz
import os
from werkzeug.utils import secure_filename
import tempfile
from app.models.inventario import InventarioGeneral


catalogos_bp = Blueprint('catalogos', __name__, url_prefix='/api/catalogos')

# Helper: Normaliza y limpia texto para comparación
def normalizar(texto):
    return (texto or '').strip().lower().replace(' ', '')

# Helper: Busca duplicados fuzzy en el catálogo indicado
def buscar_similares(model, nombre, umbral=80):
    nombre_norm = normalizar(nombre)
    existentes = [getattr(x, "nombre") for x in model.query.all()]
    similares = [
        x for x in existentes
        if fuzz.ratio(nombre_norm, normalizar(x)) >= umbral
    ]
    return similares

# Mapeo de nombre a modelo
CAT_MODELS = {
    'proveedores': Proveedor,
    'marcas': Marca,
    'unidades': UnidadMedida,
    'gruposmusculares': GrupoMuscular,
    'tipos': TipoInventario,
    'clasificaciones': CatalogoClasificacion,
    'categorias': CatalogoClasificacion,
    
}

# ══════════════════════════════════════════════
# RESPUESTA ESTÁNDAR
# ══════════════════════════════════════════════
def respuesta_ok(data=None, message=None, code=200):
    resp = {}
    if message:
        resp["message"] = message
    if data is not None:
        resp["data"] = data
    return jsonify(resp), code

# ══════════════════════════════════════════════
# GET UNIVERSAL (con filtros por cualquier campo)
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>', methods=['GET'], strict_slashes=False)
@jwt_required()
def listar_catalogo(catalogo):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)
    query = model.query

    # Aplica filtros dinámicos por args si existen en el modelo
    for key, value in request.args.items():
        if hasattr(model, key) and value:
            # Maneja tipo entero si la columna es Integer
            column = getattr(model, key)
            try:
                if str(column.type) == "INTEGER":
                    value = int(value)
            except:
                pass
            query = query.filter(column == value)

    resultados = query.order_by(model.id.desc()).all()
    res = []
    for r in resultados:
        item = {"id": r.id, "nombre": r.nombre}
        # Extrae todos los campos relevantes dinámicamente
        for c in r.__table__.columns:
            if c.name not in ("id", "nombre"):
                item[c.name] = getattr(r, c.name)
        res.append(item)
    return respuesta_ok(res)

# ══════════════════════════════════════════════
# POST UNIVERSAL (campos extra dinámicos)
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>', methods=['POST'], strict_slashes=False)
@jwt_required()
def crear_catalogo(catalogo):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)
    data = request.get_json()
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return respuesta_ok(message="El nombre es obligatorio", code=400)
    similares = buscar_similares(model, nombre, umbral=80)
    forzar = request.args.get('forzar', 'false').lower() == 'true'
    if similares and not forzar:
        return respuesta_ok({
            "similares": similares,
            "forzar": True
        }, message=f"Posible duplicado detectado: {similares}", code=409)

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
# PUT UNIVERSAL (campos extra dinámicos)
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>/<int:elemento_id>', methods=['PUT'], strict_slashes=False)
@jwt_required()
def editar_catalogo(catalogo, elemento_id):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)
    data = request.get_json()
    elemento = model.query.get(elemento_id)
    if not elemento:
        return respuesta_ok(message="Elemento no encontrado", code=404)

    if 'nombre' in data:
        elemento.nombre = data['nombre'].strip()
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
@catalogos_bp.route('/<string:catalogo>/<int:elemento_id>', methods=['DELETE'], strict_slashes=False)
@jwt_required()
def eliminar_catalogo(catalogo, elemento_id):
    model = CAT_MODELS.get(catalogo.lower())
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
# BÚSQUEDA FUZZY UNIVERSAL
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>/buscar', methods=['GET'])
@jwt_required()
def buscar_catalogo(catalogo):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)
    termino = request.args.get('q', '').strip()
    if not termino:
        return respuesta_ok([])
    resultados = [
        {
            "id": r.id,
            "nombre": r.nombre,
            **{c.name: getattr(r, c.name) for c in r.__table__.columns if c.name not in ("id", "nombre")}
        }
        for r in model.query.all()
        if fuzz.ratio(normalizar(termino), normalizar(r.nombre)) >= 70
    ]
    return respuesta_ok(resultados)

# ══════════════════════════════════════════════
# DROPDOWN UNIVERSAL (label/id)
# ══════════════════════════════════════════════
@catalogos_bp.route('/dropdown/<string:catalogo>', methods=['GET'], strict_slashes=False)
@jwt_required()
def dropdown_catalogo(catalogo):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)
    data = [{"id": r.id, "label": r.nombre} for r in model.query.order_by(model.nombre).all()]
    return respuesta_ok(data)

# ══════════════════════════════════════════════
# ENDPOINTS ESPECIALES (relaciones, combos dependientes, etc)
# ══════════════════════════════════════════════



@catalogos_bp.route('/<string:catalogo>/importar', methods=['POST'], strict_slashes=False)
@jwt_required()
def importar_catalogo(catalogo):
    import re
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)
    if 'file' not in request.files:
        return respuesta_ok(message="No se subió archivo", code=400)
    file = request.files['file']
    filename = secure_filename(file.filename)
    tmp_dir = tempfile.gettempdir()
    filepath = os.path.join(tmp_dir, filename)
    file.save(filepath)

    
    # Detecta tipo de archivo y lee como corresponde
    if filename.lower().endswith('.csv'):
        import chardet

        # Detecta encoding
        with open(filepath, 'rb') as f:
            result = chardet.detect(f.read())
            encoding = result['encoding'] or 'utf-8'

        df = pd.read_csv(filepath, encoding=encoding)
    else:
        df = pd.read_excel(filepath)

    # FUNCION DE LIMPIEZA
    def limpiar_texto(texto):
        if pd.isna(texto):
            return ''
        texto = str(texto)
        texto = ' '.join(texto.strip().split())  # Quitar espacios extra
        # Primera letra mayúscula por palabra, resto minúscula
        texto = ' '.join(w.capitalize() for w in texto.lower().split())
        # Quitar caracteres especiales, excepto letras/números/espacio y acentos
        texto = re.sub(r'[^\w áéíóúüñÁÉÍÓÚÜÑ]', '', texto)
        return texto

    agregados, ignorados, errores = 0, 0, 0
    for idx, row in df.iterrows():
        try:
            campos = {c: row[c] for c in row.index if c in model.__table__.columns.keys()}
            # Limpiar todos los campos string
            for key in campos:
                if isinstance(campos[key], str) or not pd.isna(campos[key]):
                    if isinstance(campos[key], str):
                        campos[key] = limpiar_texto(campos[key])
            existe = model.query.filter_by(nombre=campos.get('nombre')).first()
            if not existe:
                nuevo = model(**campos)
                db.session.add(nuevo)
                agregados += 1
            else:
                ignorados += 1
        except Exception as e:
            errores += 1
            print(f"Error en la fila {idx+2}: {e}, datos: {row}")  # +2 por header + index base 0

    db.session.commit()
    
    os.remove(filepath)
    
    return respuesta_ok(
        message=f"Carga masiva exitosa. Agregados: {agregados}, Duplicados ignorados: {ignorados}, Errores: {errores}"
    )


@catalogos_bp.route('/<string:catalogo>/exportar', methods=['GET'], strict_slashes=False)
@jwt_required()
def exportar_catalogo(catalogo):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return respuesta_ok(message="Catálogo inválido", code=400)
    registros = model.query.all()
    data = [{c.name: getattr(r, c.name) for c in model.__table__.columns} for r in registros]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f'{catalogo}.xlsx')
    
    
@catalogos_bp.route('/clasificaciones/arbol', methods=['GET'])
@jwt_required()
def arbol_clasificaciones():
    departamento_id = request.args.get('departamento_id', type=int)

    def build_tree(parent_id, departamento_id, nivel=1):
        q = CatalogoClasificacion.query.filter_by(parent_id=parent_id)
        if departamento_id:
            q = q.filter_by(departamento_id=departamento_id)
        nodos = q.all()
        return [
            {
                "id": n.id,
                "nombre": n.nombre,
                "nivel": n.nivel,
                "parent_id": n.parent_id,
                "departamento_id": n.departamento_id,
                "hijos": build_tree(n.id, departamento_id, n.nivel + 1)
            } for n in nodos
        ]
    
    if departamento_id:
        arbol = build_tree(None, departamento_id)
        return respuesta_ok(arbol)
    else:
        # TODOS los árboles raíz, uno por departamento
        # primero encuentra todos los departamentos únicos
        deptos = db.session.query(CatalogoClasificacion.departamento_id).distinct().all()
        arbol = []
        for d in deptos:
            dep_id = d[0]
            subarbol = build_tree(None, dep_id)
            arbol.append({
                "departamento_id": dep_id,
                "arbol": subarbol
            })
    return respuesta_ok(arbol)



@catalogos_bp.route('/clasificaciones/todos', methods=['GET'])
@jwt_required()
def todas_las_clasificaciones():
    print(">>> Entrando a todas_las_clasificaciones()")
    clasifs = CatalogoClasificacion.query.all()
    data = [{'id': c.id, 'nombre': c.nombre} for c in clasifs]
    return jsonify({'data': data})


@catalogos_bp.route('/inventario/categorias', methods=['GET'], strict_slashes=False)
@jwt_required()
def categorias_inventario_distintas():
    """
    Devuelve categorías únicas reales del inventario (InventarioGeneral.categoria).
    Evita mezclar con 'clasificaciones' de tickets.
    """
    try:
        # Distintas + ordenadas (case-insensitive)
        rows = db.session.query(InventarioGeneral.categoria).filter(
            InventarioGeneral.categoria.isnot(None),
            InventarioGeneral.categoria != ''
        ).distinct().all()

        # rows = [('Limpieza',), ('Maquinas',), ...]
        categorias = sorted(
            { (r[0] or '').strip() for r in rows if (r[0] or '').strip() },
            key=lambda s: s.lower()
        )

        data = [{"id": i+1, "nombre": nombre} for i, nombre in enumerate(categorias)]
        return respuesta_ok(data)
    except Exception as e:
        return manejar_error(e, "categorias_inventario_distintas")