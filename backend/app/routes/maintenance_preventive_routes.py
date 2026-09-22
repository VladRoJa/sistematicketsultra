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
    previsualizar_capacidad_programacion,
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
from app.services.maintenance_my_program_service import (
    MaintenanceMyProgramError,
    build_my_program,
)
from app.services.maintenance_execution_service import (
    MaintenanceExecutionError,
    complete_preventive,
    create_preventive_bitacora,
    get_work_detail,
)
from app.services.ticket_attachment_service import (
    create_ticket_image_attachment,
)
from app.services.ticket_attachment_image_service import (
    MAX_TICKET_ATTACHMENT_BYTES,
)
from app.services.maintenance_checklist_service import (
    MaintenanceChecklistError,
    actualizar_item_checklist,
    actualizar_template_checklist,
    agregar_item_checklist,
    crear_template_checklist,
    listar_catalogo_checklists,
    serialize_item,
    serialize_template,
)
from app.services.maintenance_weekly_dashboard_service import (
    MaintenanceWeeklyDashboardError,
    build_dashboard_drilldown,
    build_weekly_dashboard,
    get_dashboard_context,
)
from app.services.maintenance_reprogram_service import (
    MaintenanceReprogramError,
    actualizar_motivo_reprogramacion,
    crear_motivo_reprogramacion,
    listar_motivos_reprogramacion,
    reprogramar_ticket_mantenimiento,
    serializar_motivo_reprogramacion,
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
    if isinstance(exc, MaintenanceMyProgramError):
        return jsonify({"mensaje": str(exc)}), exc.status_code
    if isinstance(exc, MaintenanceExecutionError):
        return jsonify({"mensaje": str(exc)}), exc.status_code
    if isinstance(exc, MaintenanceChecklistError):
        return jsonify({"mensaje": str(exc)}), exc.status_code
    if isinstance(exc, MaintenanceWeeklyDashboardError):
        return jsonify({"mensaje": str(exc)}), exc.status_code
    if isinstance(exc, MaintenanceReprogramError):
        return jsonify({"mensaje": str(exc)}), exc.status_code
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


@maintenance_preventive_bp.route(
    "/reprogram-reasons",
    methods=["GET"],
)
@jwt_required()
def get_reprogram_reasons():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    include_inactive = str(
        request.args.get("include_inactive") or ""
    ).strip().lower() in {"1", "true", "yes", "si", "sí"}

    try:
        return jsonify({
            "reasons": listar_motivos_reprogramacion(
                user,
                include_inactive=include_inactive,
            )
        }), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/reprogram-reasons",
    methods=["POST"],
)
@jwt_required()
def post_reprogram_reason():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        reason = crear_motivo_reprogramacion(
            user,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify(
            serializar_motivo_reprogramacion(reason)
        ), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/reprogram-reasons/<int:reason_id>",
    methods=["PUT"],
)
@jwt_required()
def put_reprogram_reason(reason_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        reason = actualizar_motivo_reprogramacion(
            user,
            reason_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify(
            serializar_motivo_reprogramacion(reason)
        ), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/tickets/<int:ticket_id>/reprogram",
    methods=["POST"],
)
@jwt_required()
def post_reprogram_maintenance_ticket(ticket_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        ticket = reprogramar_ticket_mantenimiento(
            user,
            ticket_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()

        return jsonify({
            "mensaje": "Mantenimiento reprogramado.",
            "ticket_id": int(ticket.id),
            "tipo_mantenimiento": ticket.tipo_mantenimiento,
            "fecha_compromiso_original": (
                ticket.fecha_compromiso_original.isoformat()
                if ticket.fecha_compromiso_original
                else None
            ),
            "fecha_solucion": (
                ticket.fecha_solucion.isoformat()
                if ticket.fecha_solucion
                else None
            ),
            "fecha_programada_original": (
                ticket.fecha_programada_original.isoformat()
                if ticket.fecha_programada_original
                else None
            ),
            "fecha_programada_actual": (
                ticket.fecha_programada_actual.isoformat()
                if ticket.fecha_programada_actual
                else None
            ),
        }), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/dashboard/context",
    methods=["GET"],
)
@jwt_required()
def get_maintenance_dashboard_context():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        return jsonify(get_dashboard_context(user)), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/dashboard/weekly",
    methods=["GET"],
)
@jwt_required()
def get_weekly_dashboard():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        return jsonify(
            build_weekly_dashboard(
                user,
                weeks=request.args.get("weeks", default=8, type=int),
                reference_date=request.args.get("reference_date"),
                region_id=request.args.get("region_id", type=int),
                branch_id=request.args.get("branch_id", type=int),
                crew_id=request.args.get("crew_id", type=int),
                responsible_user_id=request.args.get(
                    "responsible_user_id",
                    type=int,
                ),
            )
        ), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/dashboard/drilldown",
    methods=["GET"],
)
@jwt_required()
def get_weekly_dashboard_drilldown():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    week_start = request.args.get("week_start")
    metric = str(request.args.get("metric") or "").strip()

    if not week_start or not metric:
        return jsonify({
            "mensaje": "week_start y metric son obligatorios."
        }), 400

    try:
        return jsonify(
            build_dashboard_drilldown(
                user,
                week_start=week_start,
                metric=metric,
                region_id=request.args.get("region_id", type=int),
                branch_id=request.args.get("branch_id", type=int),
                crew_id=request.args.get("crew_id", type=int),
                responsible_user_id=request.args.get(
                    "responsible_user_id",
                    type=int,
                ),
            )
        ), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/checklists", methods=["GET"])
@jwt_required()
def get_checklists():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        return jsonify(listar_catalogo_checklists(user)), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route("/checklists", methods=["POST"])
@jwt_required()
def post_checklist():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        template = crear_template_checklist(
            user,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify(serialize_template(template)), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/checklists/<int:template_id>",
    methods=["PUT"],
)
@jwt_required()
def put_checklist(template_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        template = actualizar_template_checklist(
            user,
            template_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify(serialize_template(template)), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/checklists/<int:template_id>/items",
    methods=["POST"],
)
@jwt_required()
def post_checklist_item(template_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        item = agregar_item_checklist(
            user,
            template_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify(serialize_item(item)), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/checklists/<int:template_id>/items/<int:item_id>",
    methods=["PUT"],
)
@jwt_required()
def put_checklist_item(template_id: int, item_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        item = actualizar_item_checklist(
            user,
            template_id,
            item_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return jsonify(serialize_item(item)), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/my-program/<int:ticket_id>",
    methods=["GET"],
)
@jwt_required()
def get_my_program_ticket(ticket_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        return jsonify(get_work_detail(user, ticket_id)), 200
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/my-program/<int:ticket_id>/bitacora",
    methods=["POST"],
)
@jwt_required()
def post_my_program_bitacora(ticket_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        result = create_preventive_bitacora(
            user,
            ticket_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()

        return jsonify({
            "mensaje": "Bitácora preventiva guardada.",
            "bitacora_id": result["bitacora"].id,
            "correctivo_id": (
                result["corrective"].id
                if result["corrective"] is not None
                else None
            ),
        }), 201
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/my-program/<int:ticket_id>/evidence",
    methods=["POST"],
)
@jwt_required()
def post_my_program_evidence(ticket_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    file = request.files.get("image")
    if file is None:
        return jsonify({"mensaje": "Debes adjuntar image."}), 400

    try:
        detail = get_work_detail(user, ticket_id)
        if not detail["bitacoras"]:
            return jsonify({
                "mensaje": (
                    "Guarda la bitácora antes de adjuntar evidencia."
                )
            }), 409

        if detail["has_evidence"]:
            return jsonify({
                "mensaje": (
                    "Este intento preventivo ya tiene evidencia adjunta."
                )
            }), 409

        content = file.read(MAX_TICKET_ATTACHMENT_BYTES + 1)
        if len(content) > MAX_TICKET_ATTACHMENT_BYTES:
            return jsonify({
                "mensaje": "La imagen excede el límite máximo de 15 MB."
            }), 400

        attachment = create_ticket_image_attachment(
            ticket_id=ticket_id,
            content=content,
            original_filename=file.filename or "evidencia.jpg",
            declared_mime_type=file.mimetype,
            allow_additional=True,
        )

        return jsonify({
            "mensaje": "Evidencia guardada.",
            "attachment_id": attachment.id,
        }), 201
    except ValueError as exc:
        return jsonify({"mensaje": str(exc)}), 400
    except Exception as exc:
        return _error_response(exc)


@maintenance_preventive_bp.route(
    "/my-program/<int:ticket_id>/complete",
    methods=["POST"],
)
@jwt_required()
def post_my_program_complete(ticket_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        ticket = complete_preventive(user, ticket_id)
        db.session.commit()

        return jsonify({
            "mensaje": "Preventivo realizado; pendiente de validación.",
            "ticket_id": ticket.id,
            "estado": ticket.estado,
            "estado_cierre": ticket.estado_cierre,
        }), 200
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)


@maintenance_preventive_bp.route("/my-program", methods=["GET"])
@jwt_required()
def get_my_program():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        return jsonify(
            build_my_program(
                user,
                start_date=request.args.get("start_date"),
                end_date=request.args.get("end_date"),
            )
        ), 200
    except Exception as exc:
        return _error_response(exc)


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
        context = listar_contexto_programacion(user)

        equipment_catalog: list[dict] = []
        for branch in context.get("sucursales", []):
            branch_id = int(branch["id"])
            branch_name = str(branch["nombre"])

            for equipment in listar_equipos_programables(
                user,
                branch_id,
            ):
                family = equipment.get("familia") or {}
                equipment_catalog.append({
                    "sucursal": branch_name,
                    "codigo_interno": equipment.get("codigo_interno"),
                    "nombre": equipment.get("nombre"),
                    "familia": family.get("nombre"),
                })

        content = build_preventive_template_xlsx(
            sucursales=[
                row["nombre"]
                for row in context.get("sucursales", [])
            ],
            responsables=[
                row["username"]
                for row in context.get("responsables", [])
            ],
            equipos=equipment_catalog,
            building_classifications=[
                row["label"]
                for row in context.get(
                    "building_classifications",
                    [],
                )
            ],
        )
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
    "/batches/<int:batch_id>/capacity-preview",
    methods=["POST"],
)
@jwt_required()
def post_batch_capacity_preview(batch_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        preview = previsualizar_capacidad_programacion(
            batch_id,
            user,
            request.get_json(silent=True) or {},
        )
        return jsonify(preview), 200
    except Exception as exc:
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
