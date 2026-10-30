"""E4 Bloque 1: recepción de levantamientos, solo piloto corporativo.
No hay endpoints de conciliar, cerrar, aprobar, ajustar ni alta de inventario.
"""
from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.inventario_levantamiento import (
    InventarioLevantamientoORM as Lev,
    InventarioLevantamientoImportacionORM as Imp,
)
from app.services.inventario_levantamientos_service import (
    E4Error, parse_uuid, crear_levantamiento, recibir_excel, recibir_excel_por_control,
    detalle_levantamiento, detalle_importacion, _private_path,
)

from app.services.inventario_levantamiento_conciliacion_service import (
    tablero_e4, cerrar_e4,
)

from app.services.inventario_levantamiento_revision_service import listado_revisiones

inventario_levantamientos_bp = Blueprint("inventario_levantamientos", __name__)


def _actor():
    """Rol REAL consultado en DB; GERENTE/GERENTE_REGIONAL siempre denegados."""
    identity = get_jwt_identity()
    if isinstance(identity, bool):
        raise E4Error(401, "SESION_INVALIDA", "Sesión inválida")
    try:
        uid = int(identity)
    except (ValueError, TypeError, OverflowError) as exc:
        raise E4Error(401, "SESION_INVALIDA", "Sesión inválida") from exc
    if uid <= 0:
        raise E4Error(401, "SESION_INVALIDA", "Sesión inválida")
    row = db.session.execute(sql_text("SELECT rol FROM users WHERE id=:id"), {"id": uid}).first()
    if row is None:
        raise E4Error(401, "SESION_INVALIDA", "Usuario inexistente")
    if str(row[0] or "").strip().upper() not in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}:
        raise E4Error(403, "E4_NO_HABILITADO", "E4 no habilitado para este perfil")
    return uid


def _id(raw):
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or int(raw) <= 0:
        raise E4Error(400, "ID_INVALIDO", "sucursal_id debe ser entero positivo")
    return int(raw)


def _bytes(file, limit):
    if file is None or not file.filename:
        raise E4Error(400, "ARCHIVO_REQUERIDO", "Adjunta el archivo")
    data = file.read(limit + 1)
    if len(data) > limit:
        raise E4Error(413, "ARCHIVO_GRANDE", "Archivo demasiado grande")
    if not data:
        raise E4Error(400, "ARCHIVO_VACIO", "Archivo vacío")
    return data


@inventario_levantamientos_bp.errorhandler(E4Error)
def _failure(error):
    db.session.rollback()
    return jsonify({"error": error.code, "detail": str(error)}), error.status


@inventario_levantamientos_bp.post("/recepciones")
@jwt_required()
def recibir_entrega_universal_e4():
    """Un input XLSX; backend identifica el ciclo sin IDs ni CSV del operador."""
    uid = _actor()
    if request.content_length and request.content_length > 12 * 1024 * 1024:
        raise E4Error(413, "ARCHIVO_GRANDE", "Solicitud demasiado grande")
    key = parse_uuid(request.form.get("idempotency_key"))
    file = request.files.get("file")
    raw = _bytes(file, 10 * 1024 * 1024)
    if not file.filename.lower().endswith(".xlsx"):
        raise E4Error(400, "EXTENSION_INVALIDA", "Se requiere archivo XLSX")
    try:
        resultado = recibir_excel_por_control(uid, key, file.filename, raw)
    except IntegrityError:
        db.session.rollback()
        raise E4Error(409, "CONFLICTO_CONCURRENTE",
                      "Recepción concurrente; actualiza la bandeja")
    return jsonify(resultado), 200 if resultado["replayed"] else 201


@inventario_levantamientos_bp.post("")
@jwt_required()
def crear_e4():
    uid = _actor()
    if request.content_length and request.content_length > 12 * 1024 * 1024:
        raise E4Error(413, "ARCHIVO_GRANDE", "Solicitud demasiado grande")
    branch = _id(request.form.get("sucursal_id"))
    origin = request.form.get("origen_corte")
    key = parse_uuid(request.form.get("cycle_key"))
    baseline = None
    if origin == "CSV_HISTORICO":
        upload = request.files.get("baseline_csv")
        if not upload or not upload.filename.lower().endswith(".csv"):
            raise E4Error(400, "CSV_REQUERIDO", "Se necesita el CSV histórico original")
        baseline = _bytes(upload, 5 * 1024 * 1024)
    result, replay = crear_levantamiento(
        uid, branch, origin, key, request.form.get("fecha_corte_local"),
        request.form.get("responsable"), baseline,
    )
    return jsonify({"levantamiento": result, "replayed": replay}), 200 if replay else 201


@inventario_levantamientos_bp.get("")
@jwt_required()
def listar_e4():
    """Bandeja de recepciones: permisos corporativos y paginación en servidor."""
    _actor()
    raw_page = request.args.get("page", "1")
    raw_size = request.args.get("per_page", "20")
    if (not raw_page.isascii() or not raw_page.isdecimal() or int(raw_page) < 1
            or not raw_size.isascii() or not raw_size.isdecimal()
            or not 1 <= int(raw_size) <= 100):
        raise E4Error(400, "PAGINACION_INVALIDA", "Paginación inválida")
    page, size = int(raw_page), int(raw_size)
    query = db.session.query(Lev, Imp).outerjoin(Imp, Lev.ultima_importacion_id == Imp.id)
    branch_raw = request.args.get("sucursal_id")
    if branch_raw is not None:
        query = query.filter(Lev.sucursal_id == _id(branch_raw))
    estado = request.args.get("estado")
    if estado:
        if estado not in {"PREPARATION", "IN_PROGRESS"}:
            raise E4Error(400, "ESTADO_INVALIDO", "Estado no permitido")
        query = query.filter(Lev.estado == estado)
    total = query.count()
    resultados = (query.order_by(Lev.creado_en_utc.desc(), Lev.id.desc())
                  .offset((page - 1) * size).limit(size).all())
    items = []
    for lev, imp in resultados:
        item = _serialize_lev_resumen(lev)
        if imp is not None:
            resumen = imp.resumen or {}
            item["importacion_actual"] = {
                "id": imp.id, "version": imp.version, "resultado": imp.resultado,
                "si": resumen.get("si", 0), "no": resumen.get("no", 0),
                "sin_revisar": resumen.get("sin_revisar", 0),
                "hallazgos": resumen.get("hallazgos", 0),
                "errores": resumen.get("errores", 0), "avisos": resumen.get("avisos", 0),
            }
        else:
            item["importacion_actual"] = None
        items.append(item)
    return jsonify({"items": items, "total": total, "page": page, "per_page": size}), 200


def _serialize_lev_resumen(lev):
    """Proyección liviana para no enviar el JSON de 12 mil filas a la bandeja."""
    return {
        "id": lev.id, "cycle_key": str(lev.cycle_key),
        "sucursal_id": lev.sucursal_id, "estado": lev.estado,
        "origen_corte": lev.origen_corte, "modalidad": lev.modalidad,
        "responsable": lev.responsable,
        "fecha_corte_local": lev.fecha_corte_local.isoformat() if lev.fecha_corte_local else None,
        "referencias_esperadas": (lev.baseline_resumen or {}).get("referencias_esperadas", 0),
        "ultima_importacion_id": lev.ultima_importacion_id,
    }


@inventario_levantamientos_bp.get("/<int:levantamiento_id>")
@jwt_required()
def detalle_e4(levantamiento_id):
    _actor()
    return jsonify(detalle_levantamiento(levantamiento_id)), 200


@inventario_levantamientos_bp.post("/<int:levantamiento_id>/importaciones")
@jwt_required()
def importar_e4(levantamiento_id):
    uid = _actor()
    if request.content_length and request.content_length > 12 * 1024 * 1024:
        raise E4Error(413, "ARCHIVO_GRANDE", "Solicitud demasiado grande")
    key = parse_uuid(request.form.get("idempotency_key"))
    file = request.files.get("file")
    raw = _bytes(file, 10 * 1024 * 1024)
    try:
        result, replay = recibir_excel(uid, levantamiento_id, key, file.filename, raw)
    except IntegrityError:
        db.session.rollback()
        raise E4Error(409, "CONFLICTO_CONCURRENTE", "Importación concurrente; consultar versión vigente")
    return jsonify({"importacion": result, "replayed": replay}), 200 if replay else 201


@inventario_levantamientos_bp.get("/<int:levantamiento_id>/importaciones/<int:importacion_id>")
@jwt_required()
def detalle_import_e4(levantamiento_id, importacion_id):
    _actor()
    return jsonify(detalle_importacion(levantamiento_id, importacion_id)), 200


@inventario_levantamientos_bp.get("/<int:levantamiento_id>/importaciones/<int:importacion_id>/archivo")
@jwt_required()
def archivo_e4(levantamiento_id, importacion_id):
    _actor()
    imp = Imp.query.filter_by(id=importacion_id, levantamiento_id=levantamiento_id).first()
    if imp is None:
        raise E4Error(404, "IMPORTACION_DESCONOCIDA", "Archivo no encontrado")
    path = _private_path(imp.storage_key)
    if not path.is_file():
        raise E4Error(409, "ARCHIVO_NO_DISPONIBLE", "El original archivado no está disponible")
    return send_file(path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=imp.original_filename)


@inventario_levantamientos_bp.get("/<int:levantamiento_id>/revisiones")
@jwt_required()
def consultar_revisiones_automaticas(levantamiento_id):
    _actor()
    raw_page = request.args.get("page", "1")
    raw_size = request.args.get("per_page", "20")
    if (not raw_page.isascii() or not raw_page.isdecimal()
            or not 1 <= int(raw_page) <= 100000
            or not raw_size.isascii() or not raw_size.isdecimal()
            or not 1 <= int(raw_size) <= 100):
        raise E4Error(400, "PAGINACION_INVALIDA", "Paginación inválida")
    return jsonify(listado_revisiones(levantamiento_id, int(raw_page), int(raw_size))), 200


@inventario_levantamientos_bp.get("/<int:levantamiento_id>/conciliacion")
@jwt_required()
def consultar_conciliacion_e4(levantamiento_id):
    _actor()
    return jsonify(tablero_e4(levantamiento_id)), 200


@inventario_levantamientos_bp.post("/<int:levantamiento_id>/cerrar")
@jwt_required()
def cerrar_levantamiento_e4(levantamiento_id):
    uid = _actor()
    try:
        resultado, replay = cerrar_e4(
            levantamiento_id, uid, request.get_json(silent=True))
    except IntegrityError:
        db.session.rollback()
        raise E4Error(409, "CONFLICTO_CONCURRENTE", "Cierre simultáneo; actualiza el expediente")
    return jsonify({"cierre": resultado, "replayed": replay}), 200 if replay else 201
