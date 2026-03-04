# backend\app\routes\pm_routes.py

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, date, timedelta
from sqlalchemy import func
from app.extensions import db
from app.models.pm_bitacora import PmBitacoraORM
from app.models.pm_preventivo import PmPreventivoConfigORM
from app.models.inventario import InventarioGeneral, InventarioSucursal
from app.models.sucursal_model import Sucursal

pm_bp = Blueprint("pm", __name__)

# ── Admin roles (reutilizado en todos los checks) ──
_ADMIN_ROLES = {"ADMINISTRADOR", "SUPER_ADMIN", "ADMIN"}


# ────────────────────────────────────────────────────────────
# HELPER: verificar permiso de sucursal por rol
# ────────────────────────────────────────────────────────────

def _verificar_permiso_sucursal(claims, sucursal_id_int):
    """
    Valida que el token tenga acceso a la sucursal indicada.
    Retorna None si OK, o (response_dict, status_code) si denegado.
    """
    rol = (claims.get("rol") or "").strip().upper()

    if rol in _ADMIN_ROLES:
        return None

    if rol == "MANTENIMIENTO":
        return None

    if rol == "AUX_MANTENIMIENTO":
        user_sucursal = claims.get("sucursal_id")
        try:
            user_sucursal = int(user_sucursal) if user_sucursal is not None else None
        except Exception:
            user_sucursal = None

        if not user_sucursal or sucursal_id_int != user_sucursal:
            return (
                {"error": "Forbidden", "detail": "No tienes acceso a esta sucursal"},
                403,
            )
        return None

    # SR_MANTENIMIENTO y otros: solo sucursales_ids del token
    allowed = claims.get("sucursales_ids") or []
    try:
        allowed = [int(x) for x in allowed]
    except Exception:
        allowed = []

    if sucursal_id_int not in allowed:
        return (
            {"error": "Forbidden", "detail": "No tienes acceso a esta sucursal"},
            403,
        )
    return None


# ────────────────────────────────────────────────────────────
# HELPER: crear bitácora (validación + inserción)
# ────────────────────────────────────────────────────────────

def _crear_bitacora(data, claims, user_id):
    """
    Valida, verifica permisos e inserta una PmBitacoraORM.
    Retorna (bitacora, None) si OK, o (None, (response_dict, status_code)) si error.
    """
    inventario_id = data.get("inventario_id")
    sucursal_id = data.get("sucursal_id")
    fecha = data.get("fecha")        # "YYYY-MM-DD"
    resultado = data.get("resultado")  # "OK" | "FALLA" | "OBS"
    notas = data.get("notas") or ""
    checks = data.get("checks") or {}

    # 1) Validación de requeridos
    if not inventario_id or not sucursal_id or not fecha or not resultado:
        return None, (
            {"error": "Bad Request", "detail": "Campos requeridos: inventario_id, sucursal_id, fecha, resultado"},
            400,
        )

    # 2) Validación checks
    if not isinstance(checks, dict):
        return None, (
            {"error": "Bad Request", "detail": "checks debe ser un objeto/dict"},
            400,
        )

    # 3) Normalizar IDs a int
    try:
        sucursal_id_int = int(sucursal_id)
        inventario_id_int = int(inventario_id)
    except (TypeError, ValueError):
        return None, (
            {"error": "Bad Request", "detail": "inventario_id y sucursal_id deben ser enteros"},
            400,
        )

    # 4) Política por rol
    denied = _verificar_permiso_sucursal(claims, sucursal_id_int)
    if denied:
        return None, denied

    # 5) Validar inventario↔sucursal
    rel = InventarioSucursal.query.filter_by(
        inventario_id=inventario_id_int,
        sucursal_id=sucursal_id_int,
    ).first()
    if not rel:
        return None, (
            {"error": "Bad Request", "detail": "El inventario_id no pertenece a la sucursal_id"},
            400,
        )

    # 6) Parse fecha
    try:
        fecha_date = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return None, (
            {"error": "Bad Request", "detail": "fecha debe ser YYYY-MM-DD"},
            400,
        )

    # 7) Insertar
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

    return bit, None


# ────────────────────────────────────────────────────────────
# POST /mobile/bitacoras  (contrato existente, sin cambios)
# ────────────────────────────────────────────────────────────

@pm_bp.route("/mobile/bitacoras", methods=["POST"])
@jwt_required()
def pm_mobile_crear_bitacora():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    claims = get_jwt() or {}

    bit, err = _crear_bitacora(data, claims, user_id)
    if err:
        return jsonify(err[0]), err[1]

    return jsonify({"msg": "Bitácora guardada", "id": bit.id}), 201


# ────────────────────────────────────────────────────────────
# POST /pm/preventivo/registrar
# ────────────────────────────────────────────────────────────

@pm_bp.route("/preventivo/registrar", methods=["POST"])
@jwt_required()
def pm_preventivo_registrar():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    claims = get_jwt() or {}

    bit, err = _crear_bitacora(data, claims, user_id)
    if err:
        return jsonify(err[0]), err[1]

    return jsonify({"msg": "Bitácora guardada", "id": bit.id}), 201


# ────────────────────────────────────────────────────────────
# GET /pm/preventivo/dashboard?sucursal_id=X&window_days=7
# ────────────────────────────────────────────────────────────

@pm_bp.route("/preventivo/dashboard", methods=["GET"])
@jwt_required()
def pm_preventivo_dashboard():
    claims = get_jwt() or {}

    # ── 1) Validar sucursal_id ──
    sucursal_id_raw = request.args.get("sucursal_id", type=int)
    if not sucursal_id_raw:
        return jsonify({"error": "Bad Request", "detail": "sucursal_id es requerido"}), 400

    sucursal_id_int = sucursal_id_raw

    # ── 2) Validar window_days ──
    window_days = request.args.get("window_days", default=7, type=int)
    if window_days < 1 or window_days > 90:
        return jsonify({
            "error": "Bad Request",
            "detail": "window_days debe estar entre 1 y 90",
        }), 400

    # ── 3) Scope check: misma política que _crear_bitacora ──
    denied = _verificar_permiso_sucursal(claims, sucursal_id_int)
    if denied:
        return jsonify(denied[0]), denied[1]

    # ── 4) Query eficiente ──
    # Subquery: última fecha de bitácora por (inventario_id, sucursal_id)
    ultima_fecha_sq = (
        db.session.query(
            PmBitacoraORM.inventario_id,
            PmBitacoraORM.sucursal_id,
            func.max(PmBitacoraORM.fecha).label("ultima_fecha"),
        )
        .filter(PmBitacoraORM.sucursal_id == sucursal_id_int)
        .group_by(PmBitacoraORM.inventario_id, PmBitacoraORM.sucursal_id)
        .subquery("uf")
    )

    # Query principal: configs activas + inventario + sucursal + última fecha
    rows = (
        db.session.query(
            PmPreventivoConfigORM,
            InventarioGeneral,
            Sucursal,
            ultima_fecha_sq.c.ultima_fecha,
        )
        .join(
            InventarioGeneral,
            InventarioGeneral.id == PmPreventivoConfigORM.inventario_id,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id == PmPreventivoConfigORM.sucursal_id,
        )
        .outerjoin(
            ultima_fecha_sq,
            db.and_(
                ultima_fecha_sq.c.inventario_id == PmPreventivoConfigORM.inventario_id,
                ultima_fecha_sq.c.sucursal_id == PmPreventivoConfigORM.sucursal_id,
            ),
        )
        .filter(
            PmPreventivoConfigORM.sucursal_id == sucursal_id_int,
            PmPreventivoConfigORM.activo.is_(True),
        )
        .all()
    )

    # ── 5) Clasificar ──
    hoy = date.today()
    atrasados = []
    hoy_list = []
    proximos = []

    for cfg, inv, suc, ultima_fecha in rows:
        if ultima_fecha is None:
            proxima_fecha = hoy
        else:
            proxima_fecha = ultima_fecha + timedelta(days=cfg.frecuencia_dias)

        dias_restantes = (proxima_fecha - hoy).days

        if proxima_fecha < hoy:
            estado = "ATRASADO"
        elif proxima_fecha == hoy:
            estado = "HOY"
        elif 0 < dias_restantes <= window_days:
            estado = "PROXIMO"
        else:
            estado = "AL_DIA"

        if estado == "AL_DIA":
            continue

        item = {
            "inventario_id": inv.id,
            "codigo_interno": inv.codigo_interno,
            "nombre": inv.nombre,
            "tipo": inv.tipo,
            "marca": inv.marca,
            "categoria": inv.categoria,
            "sucursal_id": suc.sucursal_id,
            "sucursal": suc.sucursal,
            "frecuencia_dias": cfg.frecuencia_dias,
            "ultima_fecha": ultima_fecha.isoformat() if ultima_fecha else None,
            "proxima_fecha": proxima_fecha.isoformat(),
            "dias_restantes": dias_restantes,
            "estado": estado,
        }

        if estado == "ATRASADO":
            atrasados.append(item)
        elif estado == "HOY":
            hoy_list.append(item)
        elif estado == "PROXIMO":
            proximos.append(item)

    return jsonify({
        "atrasados": atrasados,
        "hoy": hoy_list,
        "proximos": proximos,
    }), 200