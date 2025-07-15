# app/routes/catalogos_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.models.catalogos import Proveedor, Marca, Categoria, UnidadMedida, GrupoMuscular, TipoInventario
from app.utils.error_handler import manejar_error
from rapidfuzz import fuzz

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

# Mapea el string del catálogo al modelo SQLAlchemy
CAT_MODELS = {
    'proveedores': Proveedor,
    'marcas': Marca,
    'categorias': Categoria,
    'unidades': UnidadMedida,
    'gruposmusculares': GrupoMuscular,
    'tipos': TipoInventario,
}

# ══════════════════════════════════════════════
# RUTA: Listar todos los elementos de un catálogo
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>', methods=['GET'])
@jwt_required()
def listar_catalogo(catalogo):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return jsonify({"error": "Catálogo inválido"}), 400
    resultados = model.query.order_by(model.nombre).all()
    return jsonify([{
        "id": r.id,
        "nombre": r.nombre,
        **({"abreviatura": getattr(r, "abreviatura", None)} if hasattr(r, "abreviatura") else {})
    } for r in resultados]), 200

# ══════════════════════════════════════════════
# RUTA: Crear elemento (con validación fuzzy)
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>', methods=['POST'])
@jwt_required()
def crear_catalogo(catalogo):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return jsonify({"error": "Catálogo inválido"}), 400

    data = request.get_json()
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({"error": "El nombre es obligatorio"}), 400

    similares = buscar_similares(model, nombre, umbral=80)
    forzar = request.args.get('forzar', 'false').lower() == 'true'

    if similares and not forzar:
        return jsonify({
            "error": f"Posible duplicado detectado: {similares}",
            "similares": similares,
            "forzar": True
        }), 409

    # Campos extra (abreviatura para unidad, etc)
    campos = {}
    if hasattr(model, "abreviatura") and 'abreviatura' in data:
        campos["abreviatura"] = (data.get('abreviatura') or '').strip()

    try:
        nuevo = model(nombre=nombre, **campos)
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({"message": "Elemento creado correctamente", "id": nuevo.id}), 201
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, f"crear_{catalogo}")

# ══════════════════════════════════════════════
# RUTA: Actualizar elemento
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>/<int:elemento_id>', methods=['PUT'])
@jwt_required()
def editar_catalogo(catalogo, elemento_id):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return jsonify({"error": "Catálogo inválido"}), 400
    data = request.get_json()
    elemento = model.query.get(elemento_id)
    if not elemento:
        return jsonify({"error": "Elemento no encontrado"}), 404

    nuevo_nombre = (data.get('nombre') or '').strip()
    if nuevo_nombre:
        elemento.nombre = nuevo_nombre

    if hasattr(elemento, "abreviatura") and 'abreviatura' in data:
        elemento.abreviatura = (data.get('abreviatura') or '').strip()

    try:
        db.session.commit()
        return jsonify({"message": "Elemento actualizado"}), 200
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, f"editar_{catalogo}")

# ══════════════════════════════════════════════
# RUTA: Eliminar elemento (solo si no está en uso)
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>/<int:elemento_id>', methods=['DELETE'])
@jwt_required()
def eliminar_catalogo(catalogo, elemento_id):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return jsonify({"error": "Catálogo inválido"}), 400
    elemento = model.query.get(elemento_id)
    if not elemento:
        return jsonify({"error": "Elemento no encontrado"}), 404

    try:
        db.session.delete(elemento)
        db.session.commit()
        return jsonify({"message": "Elemento eliminado"}), 200
    except Exception as e:
        db.session.rollback()
        return manejar_error(e, f"eliminar_{catalogo}")

# ══════════════════════════════════════════════
# RUTA: Buscar por nombre (fuzzy)
# ══════════════════════════════════════════════
@catalogos_bp.route('/<string:catalogo>/buscar', methods=['GET'])
@jwt_required()
def buscar_catalogo(catalogo):
    model = CAT_MODELS.get(catalogo.lower())
    if not model:
        return jsonify({"error": "Catálogo inválido"}), 400
    termino = request.args.get('q', '').strip()
    if not termino:
        return jsonify([]), 200
    resultados = [
        {
            "id": r.id,
            "nombre": r.nombre,
            **({"abreviatura": getattr(r, "abreviatura", None)} if hasattr(r, "abreviatura") else {})
        }
        for r in model.query.all()
        if fuzz.ratio(normalizar(termino), normalizar(r.nombre)) >= 70
    ]
    return jsonify(resultados), 200
