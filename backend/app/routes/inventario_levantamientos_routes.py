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
    E4Error, parse_uuid, crear_levantamiento, recibir_excel,
    detalle_levantamiento, detalle_importacion, _private_path,
)

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
