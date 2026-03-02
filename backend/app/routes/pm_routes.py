# backend/app/routes/pm_routes.py


from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app.extensions import db
from app.models.pm_bitacora import PmBitacoraORM


pm_bp = Blueprint("pm", __name__)

@pm_bp.route("/mobile/bitacoras", methods=["POST"])
@jwt_required()
def pm_mobile_crear_bitacora():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    inventario_id = data.get("inventario_id")
    sucursal_id = data.get("sucursal_id")
    fecha = data.get("fecha")  # "YYYY-MM-DD"
    resultado = data.get("resultado")  # "OK" | "FALLA" | "OBS"
    notas = data.get("notas") or ""
    checks = data.get("checks") or {}

    if not inventario_id or not sucursal_id or not fecha or not resultado:
        return jsonify({
            "error": "Bad Request",
            "detail": "Campos requeridos: inventario_id, sucursal_id, fecha, resultado"
        }), 400

    if not isinstance(checks, dict):
        return jsonify({
            "error": "Bad Request",
            "detail": "checks debe ser un objeto/dict"
        }), 400

    try:
        fecha_date = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Bad Request", "detail": "fecha debe ser YYYY-MM-DD"}), 400

    bit = PmBitacoraORM(
        inventario_id=inventario_id,
        sucursal_id=sucursal_id,
        created_by_user_id=int(user_id) if user_id is not None else None,
        fecha=fecha_date,
        resultado=resultado,
        notas=notas,
        checks=checks,
    )

    db.session.add(bit)
    db.session.commit()

    return jsonify({
        "msg": "Bitácora guardada",
        "id": bit.id,
    }), 201