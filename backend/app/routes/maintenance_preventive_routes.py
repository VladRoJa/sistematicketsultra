# backend/app/routes/maintenance_preventive_routes.py

from __future__ import annotations

from io import BytesIO

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.user_model import UserORM
from app.services.maintenance_preventive_service import (
    MaintenancePreventiveAuthorizationError,
    MaintenancePreventiveError,
    MaintenancePreventiveNotFoundError,
    MaintenancePreventiveStateError,
    actualizar_renglon_lote,
    actualizar_cuadrilla,
    agregar_renglones_lote,
    assert_import_hash_available,
    crear_cuadrilla,
    crear_lote_preventivo,
    eliminar_renglon_lote,
    listar_contexto_programacion,
    listar_cuadrillas,
    listar_equipos_programables,
    listar_lotes_preventivos,
    listar_personal_mantenimiento,
    obtener_lote_preventivo,
    publicar_lote_preventivo,
    guardar_personal_mantenimiento,
    serializar_lote,
    validar_lote_preventivo,
)
from app.services.maintenance_preventive_import_service import (
    MAX_IMPORT_BYTES,
    build_preventive_template_xlsx,
    parse_preventive_import,
)


maintenance_preventive_bp = Blueprint(
    "maintenance_preventive",
    __name__,
)


def _current_user():
    return UserORM.get_by_id(get_jwt_identity())


def _error_response(exc: Exception):
    if isinstance(exc, MaintenancePreventiveAuthorizationError):
        return jsonify({"mensaje": str(exc)}), 403
    if isinstance(exc, MaintenancePreventiveNotFoundError):
        return jsonify({"mensaje": str(exc)}), 404
    if isinstance(exc, MaintenancePreventiveStateError):
        return jsonify({"mensaje": str(exc)}), 409
    if isinstance(exc, MaintenancePreventiveError):
        return jsonify({"mensaje": str(exc)}), 400
    raise exc


def _batch_summary(batch) -> dict:
    items = list(batch.items or [])
    return {
        "id": batch.id,
        "batch_key": batch.batch_key,
        "nombre": batch.nombre,
        "source_type": batch.source_type,
        "status": batch.status,
        "period_start": (
            batch.period_start.isoformat() if batch.period_start else None
        ),
        "period_end": (
            batch.period_end.isoformat() if batch.period_end else None
        ),
        "created_by_user_id": batch.created_by_user_id,
        "published_at": (
            batch.published_at.isoformat() if batch.published_at else None
        ),
        "total": len(items),
        "validos": sum(
            1 for item in items if item.validation_status == "VALIDO"
        ),
        "errores": sum(
            1 for item in items if item.validation_status == "ERROR"
        ),
        "pendientes": sum(
            1 for item in items if item.validation_status == "PENDIENTE"
        ),
    }


@maintenance_preventive_bp.route("/crews", methods=["GET"])
@jwt_required()
def get_crews():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        return jsonify({"crews": listar_cuadrillas(user)}), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/crews", methods=["POST"])
@jwt_required()
def post_crew():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        crew = crear_cuadrilla(
            user,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify({
            "id": crew.id,
            "nombre": crew.nombre,
            "region_id": crew.region_id,
            "activo": bool(crew.activo),
        }), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/crews/<int:crew_id>",
    methods=["PUT"],
)
@jwt_required()
def put_crew(crew_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        crew = actualizar_cuadrilla(
            crew_id,
            user,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify({
            "id": crew.id,
            "nombre": crew.nombre,
            "region_id": crew.region_id,
            "activo": bool(crew.activo),
        }), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route("/personnel", methods=["GET"])
@jwt_required()
def get_personnel():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        return jsonify(listar_personal_mantenimiento(user)), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/personnel", methods=["POST"])
@jwt_required()
def post_personnel():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        row = guardar_personal_mantenimiento(
            user,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify({"id": row.id}), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/personnel/<int:personnel_id>",
    methods=["PUT"],
)
@jwt_required()
def put_personnel(personnel_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        row = guardar_personal_mantenimiento(
            user,
            request.get_json(silent=True) or {},
            personnel_id=personnel_id,
        )
        db.session.commit()
        return jsonify({"id": row.id}), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route("/context", methods=["GET"])
@jwt_required()
def get_context():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        return jsonify(listar_contexto_programacion(user)), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/equipment", methods=["GET"])
@jwt_required()
def get_equipment():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    branch_id = request.args.get("branch_id", type=int)
    if branch_id is None:
        return jsonify({"mensaje": "branch_id es obligatorio."}), 400

    try:
        return jsonify(
            {
                "equipos": listar_equipos_programables(
                    user,
                    branch_id,
                )
            }
        ), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/template", methods=["GET"])
@jwt_required()
def get_template():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        # El guard real se evalúa reutilizando la operación de listado.
        listar_lotes_preventivos(user)
        content = build_preventive_template_xlsx()
        return send_file(
            BytesIO(content),
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            as_attachment=True,
            download_name="plantilla_programacion_preventiva.xlsx",
        )
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/imports", methods=["POST"])
@jwt_required()
def post_import():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    file = request.files.get("file")
    if file is None:
        return jsonify({"mensaje": "Debes adjuntar file."}), 400

    try:
        content = file.read(MAX_IMPORT_BYTES + 1)
        parsed = parse_preventive_import(
            filename=file.filename or "",
            content=content,
        )

        assert_import_hash_available(parsed["sha256"])

        batch = crear_lote_preventivo(
            user,
            {
                "nombre": (
                    request.form.get("nombre")
                    or parsed["filename"]
                ),
                "source_type": "ARCHIVO",
                "period_start": request.form.get("period_start"),
                "period_end": request.form.get("period_end"),
                "source_filename": parsed["filename"],
                "source_sha256": parsed["sha256"],
                "notes": request.form.get("notes"),
            },
        )

        agregar_renglones_lote(
            batch.id,
            user,
            parsed["rows"],
        )

        summary = validar_lote_preventivo(batch.id, user)

        db.session.commit()

        return jsonify(
            {
                "summary": summary,
                "batch": serializar_lote(batch),
            }
        ), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route("/batches", methods=["GET"])
@jwt_required()
def get_batches():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        batches = listar_lotes_preventivos(user)
        return jsonify(
            {
                "batches": [
                    _batch_summary(batch)
                    for batch in batches
                ]
            }
        ), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/batches", methods=["POST"])
@jwt_required()
def post_batch():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    payload = request.get_json(silent=True) or {}

    try:
        batch = crear_lote_preventivo(user, payload)
        db.session.commit()
        return jsonify(serializar_lote(batch)), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>",
    methods=["GET"],
)
@jwt_required()
def get_batch(batch_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        batch = obtener_lote_preventivo(batch_id, user)
        return jsonify(serializar_lote(batch)), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/items",
    methods=["POST"],
)
@jwt_required()
def post_batch_items(batch_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    payload = request.get_json(silent=True) or {}
    rows = payload.get("items")

    try:
        agregar_renglones_lote(batch_id, user, rows)
        batch = obtener_lote_preventivo(batch_id, user)
        db.session.commit()
        return jsonify(serializar_lote(batch)), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/items/<int:item_id>",
    methods=["PUT"],
)
@jwt_required()
def put_batch_item(batch_id: int, item_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    payload = request.get_json(silent=True) or {}

    try:
        item = actualizar_renglon_lote(
            batch_id,
            item_id,
            user,
            payload,
        )
        db.session.commit()
        return jsonify(
            {
                "mensaje": "Renglón actualizado; requiere revalidación.",
                "item": {
                    "id": item.id,
                    "validation_status": item.validation_status,
                },
            }
        ), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/items/<int:item_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_batch_item(batch_id: int, item_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        eliminar_renglon_lote(batch_id, item_id, user)
        db.session.commit()
        return jsonify({"mensaje": "Renglón eliminado."}), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/publish",
    methods=["POST"],
)
@jwt_required()
def post_publish_batch(batch_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        tickets = publicar_lote_preventivo(batch_id, user)
        batch = obtener_lote_preventivo(batch_id, user)
        db.session.commit()
        return jsonify(
            {
                "mensaje": "Lote preventivo publicado.",
                "ticket_ids": [ticket.id for ticket in tickets],
                "batch": serializar_lote(batch),
            }
        ), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/batches/<int:batch_id>/validate",
    methods=["POST"],
)
@jwt_required()
def post_validate_batch(batch_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        summary = validar_lote_preventivo(batch_id, user)
        batch = obtener_lote_preventivo(batch_id, user)
        db.session.commit()
        return jsonify(
            {
                "summary": summary,
                "batch": serializar_lote(batch),
            }
        ), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)
