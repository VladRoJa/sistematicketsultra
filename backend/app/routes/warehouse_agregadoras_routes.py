# backend/app/routes/warehouse_agregadoras_routes.py

from __future__ import annotations

from flask import Blueprint, jsonify, send_file
from flask_jwt_extended import jwt_required

from app.utils.warehouse_access import (
    require_warehouse_upload,
    require_warehouse_view,
)
from app.warehouse.services.agregadoras_consolidado_export_service import (
    AgregadorasConsolidadoError,
    generate_agregadoras_consolidado,
    get_agregadoras_consolidado_download,
    get_agregadoras_consolidado_status,
)


warehouse_agregadoras_bp = Blueprint(
    "warehouse_agregadoras",
    __name__,
)


@warehouse_agregadoras_bp.route(
    "/agregadoras-consolidado/status",
    methods=["GET"],
)
@jwt_required()
def agregadoras_consolidado_status():
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    return jsonify(get_agregadoras_consolidado_status()), 200


@warehouse_agregadoras_bp.route(
    "/agregadoras-consolidado/download",
    methods=["GET"],
)
@jwt_required()
def agregadoras_consolidado_download():
    forbidden = require_warehouse_view()
    if forbidden:
        return forbidden

    try:
        path, download_filename = get_agregadoras_consolidado_download()
    except AgregadorasConsolidadoError as exc:
        return jsonify(
            {
                "error": "Consolidado no disponible",
                "detail": str(exc),
            }
        ), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=download_filename,
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )


@warehouse_agregadoras_bp.route(
    "/agregadoras-consolidado/generate",
    methods=["POST"],
)
@jwt_required()
def agregadoras_consolidado_generate():
    forbidden = require_warehouse_upload()
    if forbidden:
        return forbidden

    try:
        result = generate_agregadoras_consolidado()
    except AgregadorasConsolidadoError as exc:
        return jsonify(
            {
                "error": "No se pudo generar el consolidado",
                "detail": str(exc),
            }
        ), 409

    return jsonify(result), 200
