from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime
from app.extensions import db
from app.models.pm_bitacora import PmBitacoraORM
from app.models.inventario import InventarioSucursal

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

    # 1) Validación mínima de requeridos
    if not inventario_id or not sucursal_id or not fecha or not resultado:
        return jsonify({
            "error": "Bad Request",
            "detail": "Campos requeridos: inventario_id, sucursal_id, fecha, resultado"
        }), 400

    # 2) Validación de estructura de checks
    if not isinstance(checks, dict):
        return jsonify({
            "error": "Bad Request",
            "detail": "checks debe ser un objeto/dict"
        }), 400

    # 3) Scope check: política final por rol + relación inventario↔sucursal
    claims = get_jwt() or {}
    rol = (claims.get("rol") or "").strip().upper()
    admin_roles = {"ADMINISTRADOR", "SUPER_ADMIN", "ADMIN"}

    # Normalizar ids a int (evita comparaciones raras)
    try:
        sucursal_id_int = int(sucursal_id)
        inventario_id_int = int(inventario_id)
    except (TypeError, ValueError):
        return jsonify({
            "error": "Bad Request",
            "detail": "inventario_id y sucursal_id deben ser enteros"
        }), 400

    # --- Política por rol ---
    if rol in admin_roles:
        pass

    elif rol == "MANTENIMIENTO":
        # Mantenimiento puede registrar en cualquier sucursal
        pass

    elif rol == "AUX_MANTENIMIENTO":
        # Aux solo en su sucursal fija (del token)
        user_sucursal = claims.get("sucursal_id")
        try:
            user_sucursal = int(user_sucursal) if user_sucursal is not None else None
        except Exception:
            user_sucursal = None

        if not user_sucursal or sucursal_id_int != user_sucursal:
            return jsonify({
                "error": "Forbidden",
                "detail": "No tienes acceso a esta sucursal"
            }), 403

    else:
        # SR_MANTENIMIENTO (y otros no-admin): solo sucursales_ids del token
        allowed = claims.get("sucursales_ids") or []
        try:
            allowed = [int(x) for x in allowed]
        except Exception:
            allowed = []

        if sucursal_id_int not in allowed:
            return jsonify({
                "error": "Forbidden",
                "detail": "No tienes acceso a esta sucursal"
            }), 403
            
    # Validar que inventario_id pertenece a la sucursal_id
    rel = InventarioSucursal.query.filter_by(
        inventario_id=inventario_id_int,
        sucursal_id=sucursal_id_int
    ).first()

    if not rel:
        return jsonify({
            "error": "Bad Request",
            "detail": "El inventario_id no pertenece a la sucursal_id"
        }), 400

    # 4) Parse fecha
    try:
        fecha_date = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({
            "error": "Bad Request",
            "detail": "fecha debe ser YYYY-MM-DD"
        }), 400

    # 5) Guardar bitácora
    bit = PmBitacoraORM(
        inventario_id=inventario_id_int,
        sucursal_id=sucursal_id_int,
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