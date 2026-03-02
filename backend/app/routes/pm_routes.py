# backend/app/routes/pm_routes.py
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

pm_bp = Blueprint("pm", __name__)

@pm_bp.route("/mobile/bitacoras", methods=["POST"])
@jwt_required()
def pm_mobile_crear_bitacora():
    """
    Endpoint móvil (MVP): recibe una bitácora de mantenimiento preventivo.
    Por ahora: valida payload y responde 201 (stub). Luego lo conectamos a BD.
    """
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    inventario_id = data.get("inventario_id")
    fecha = data.get("fecha")  # "YYYY-MM-DD"
    resultado = data.get("resultado")  # "OK" | "FALLA" | "OBS"
    notas = data.get("notas") or ""
    checks = data.get("checks") or {}

    # Validación mínima
    if not inventario_id or not fecha or not resultado:
        return jsonify({
            "error": "Bad Request",
            "detail": "Campos requeridos: inventario_id, fecha, resultado"
        }), 400

    if not isinstance(checks, dict):
        return jsonify({
            "error": "Bad Request",
            "detail": "checks debe ser un objeto/dict"
        }), 400

    # Stub: regresamos un id fake para que el móvil ya pueda seguir flujo
    return jsonify({
        "msg": "Bitácora recibida (stub)",
        "id": 1,
        "created_by": user_id,
        "inventario_id": inventario_id,
        "fecha": fecha,
        "resultado": resultado,
        "notas": notas,
        "checks": checks,
    }), 201