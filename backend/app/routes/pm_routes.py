from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, date, timedelta
from sqlalchemy import func
from app.extensions import db
from app.models.pm_bitacora import PmBitacoraORM
from app.models.pm_preventivo import PmPreventivoConfigORM
from app.models.inventario import InventarioGeneral, InventarioSucursal
from app.models.sucursal_model import Sucursal
from app.models.pm_validacion import PmValidacionORM

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
    fecha = data.get("fecha")  # "YYYY-MM-DD"
    resultado = data.get("resultado")  # "OK" | "FALLA" | "OBS"
    notas = data.get("notas") or ""
    checks = data.get("checks") or {}

    # 1) Validación de requeridos
    if not inventario_id or not sucursal_id or not fecha or not resultado:
        return None, (
            {
                "error": "Bad Request",
                "detail": "Campos requeridos: inventario_id, sucursal_id, fecha, resultado",
            },
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
            {
                "error": "Bad Request",
                "detail": "inventario_id y sucursal_id deben ser enteros",
            },
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
            {
                "error": "Bad Request",
                "detail": "El inventario_id no pertenece a la sucursal_id",
            },
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
# HELPER: crear validación PM (validación + inserción)
# ────────────────────────────────────────────────────────────
def _crear_validacion_pm(data, claims, user_id):
    """
    Valida e inserta una PmValidacionORM.
    Retorna (validacion, None) si OK, o (None, (response_dict, status_code)) si error.
    """
    bitacora_pm_id = data.get("bitacora_pm_id")
    decision = (data.get("decision") or "").strip().upper()
    motivo = (data.get("motivo") or "").strip()

    # 1) Requeridos mínimos
    if not bitacora_pm_id or not decision:
        return None, (
            {
                "error": "Bad Request",
                "detail": "Campos requeridos: bitacora_pm_id, decision",
            },
            400,
        )

    # 2) Normalizar ID
    try:
        bitacora_pm_id_int = int(bitacora_pm_id)
    except (TypeError, ValueError):
        return None, (
            {"error": "Bad Request", "detail": "bitacora_pm_id debe ser entero"},
            400,
        )

    # 3) Validar decision
    if decision not in {"VALIDADO", "RECHAZADO"}:
        return None, (
            {
                "error": "Bad Request",
                "detail": "decision debe ser VALIDADO o RECHAZADO",
            },
            400,
        )

    # 4) Motivo obligatorio al rechazar
    if decision == "RECHAZADO" and not motivo:
        return None, (
            {
                "error": "Bad Request",
                "detail": "motivo es obligatorio cuando decision es RECHAZADO",
            },
            400,
        )

    # 5) Buscar bitácora
    bitacora = db.session.get(PmBitacoraORM, bitacora_pm_id_int)
    if not bitacora:
        return None, (
            {"error": "Not Found", "detail": "La bitácora PM no existe"},
            404,
        )

    # 6) Scope check usando la sucursal de la bitácora
    denied = _verificar_permiso_sucursal(claims, bitacora.sucursal_id)
    if denied:
        return None, denied

    # 7) Evitar doble validación
    if bitacora.pm_validacion:
        return None, (
            {
                "error": "Conflict",
                "detail": "La bitácora PM ya cuenta con validación",
            },
            409,
        )

    # 8) Evitar auto-validación
    try:
        current_user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        current_user_id = None

    if current_user_id is None:
        return None, (
            {
                "error": "Unauthorized",
                "detail": "No se pudo identificar al usuario actual",
            },
            401,
        )

    if (
        bitacora.created_by_user_id is not None
        and bitacora.created_by_user_id == current_user_id
    ):
        return None, (
            {
                "error": "Forbidden",
                "detail": "No puedes validar tu propia bitácora PM",
            },
            403,
        )

    # 9) Insertar validación
    validacion = PmValidacionORM(
        bitacora_pm_id=bitacora_pm_id_int,
        decision=decision,
        motivo=motivo or None,
        validado_por_user_id=current_user_id,
    )
    db.session.add(validacion)
    db.session.commit()

    return validacion, None


# ────────────────────────────────────────────────────────────
# HELPER: serializar detalle de bitácora PM
# ────────────────────────────────────────────────────────────
def _serializar_bitacora_pm_detalle(bitacora):
    validacion = bitacora.pm_validacion

    return {
        "id": bitacora.id,
        "inventario_id": bitacora.inventario_id,
        "sucursal_id": bitacora.sucursal_id,
        "created_by_user_id": bitacora.created_by_user_id,
        "fecha": bitacora.fecha.isoformat() if bitacora.fecha else None,
        "resultado": bitacora.resultado,
        "notas": bitacora.notas,
        "checks": bitacora.checks or {},
        "created_at": bitacora.created_at.isoformat() if bitacora.created_at else None,
        "validacion": {
            "decision": validacion.decision,
            "motivo": validacion.motivo,
            "validado_por_user_id": validacion.validado_por_user_id,
            "validado_en": validacion.validado_en.isoformat()
            if validacion.validado_en
            else None,
        }
        if validacion
        else None,
    }


# ────────────────────────────────────────────────────────────
# HELPER: serializar resumen de bitácora PM para dashboard preventivo
# ────────────────────────────────────────────────────────────


def _serializar_bitacora_pm_resumen(bitacora, inventario, sucursal, validacion):
    return {
        "id": bitacora.id,
        "inventario_id": bitacora.inventario_id,
        "codigo_interno": inventario.codigo_interno,
        "nombre": inventario.nombre,
        "sucursal_id": bitacora.sucursal_id,
        "sucursal": sucursal.sucursal,
        "fecha": bitacora.fecha.isoformat() if bitacora.fecha else None,
        "resultado": bitacora.resultado,
        "notas": bitacora.notas,
        "created_at": bitacora.created_at.isoformat() if bitacora.created_at else None,
        "created_by_user_id": bitacora.created_by_user_id,
        "estado_validacion": validacion.decision if validacion else "SIN_VALIDACION",
    }


# ────────────────────────────────────────────────────────────
# POST /mobile/bitacoras
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
# POST /preventivo/registrar
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
# POST /validaciones
# ────────────────────────────────────────────────────────────
@pm_bp.route("/validaciones", methods=["POST"])
@jwt_required()
def pm_crear_validacion():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    claims = get_jwt() or {}

    validacion, err = _crear_validacion_pm(data, claims, user_id)
    if err:
        return jsonify(err[0]), err[1]

    return jsonify(
        {
            "msg": "Validación PM guardada",
            "id": validacion.id,
            "bitacora_pm_id": validacion.bitacora_pm_id,
            "decision": validacion.decision,
        }
    ), 201


# ────────────────────────────────────────────────────────────
# GET /bitacoras/<id>
# ────────────────────────────────────────────────────────────
@pm_bp.route("/bitacoras/<int:bitacora_pm_id>", methods=["GET"])
@jwt_required()
def pm_obtener_bitacora_detalle(bitacora_pm_id):
    claims = get_jwt() or {}

    bitacora = db.session.get(PmBitacoraORM, bitacora_pm_id)
    if not bitacora:
        return jsonify(
            {
                "error": "Not Found",
                "detail": "La bitácora PM no existe",
            }
        ), 404

    denied = _verificar_permiso_sucursal(claims, bitacora.sucursal_id)
    if denied:
        return jsonify(denied[0]), denied[1]

    return jsonify(_serializar_bitacora_pm_detalle(bitacora)), 200

# ────────────────────────────────────────────────────────────
# listar bitácoras PM con filtros (sucursal_id, fecha_desde, fecha_hasta)
# ────────────────────────────────────────────────────────────



@pm_bp.route("/bitacoras", methods=["GET"])
@jwt_required()
def pm_listar_bitacoras():
    claims = get_jwt() or {}

    sucursal_id = request.args.get("sucursal_id", type=int)
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")

    query = (
        db.session.query(
            PmBitacoraORM,
            InventarioGeneral,
            Sucursal,
            PmValidacionORM,
        )
        .join(
            InventarioGeneral,
            InventarioGeneral.id == PmBitacoraORM.inventario_id,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id == PmBitacoraORM.sucursal_id,
        )
        .outerjoin(
            PmValidacionORM,
            PmValidacionORM.bitacora_pm_id == PmBitacoraORM.id,
        )
    )

    if sucursal_id:
        denied = _verificar_permiso_sucursal(claims, sucursal_id)
        if denied:
            return jsonify(denied[0]), denied[1]
        query = query.filter(PmBitacoraORM.sucursal_id == sucursal_id)
    else:
        rol = (claims.get("rol") or "").strip().upper()

        if rol not in _ADMIN_ROLES and rol != "MANTENIMIENTO":
            if rol == "AUX_MANTENIMIENTO":
                user_sucursal = claims.get("sucursal_id")
                try:
                    user_sucursal = int(user_sucursal) if user_sucursal is not None else None
                except Exception:
                    user_sucursal = None

                if not user_sucursal:
                    return jsonify({"error": "Forbidden", "detail": "No tienes acceso a sucursales"}), 403

                query = query.filter(PmBitacoraORM.sucursal_id == user_sucursal)
            else:
                allowed = claims.get("sucursales_ids") or []
                try:
                    allowed = [int(x) for x in allowed]
                except Exception:
                    allowed = []

                if not allowed:
                    return jsonify({"error": "Forbidden", "detail": "No tienes acceso a sucursales"}), 403

                query = query.filter(PmBitacoraORM.sucursal_id.in_(allowed))

    if fecha_desde:
        try:
            fecha_desde_date = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
            query = query.filter(PmBitacoraORM.fecha >= fecha_desde_date)
        except ValueError:
            return jsonify({"error": "Bad Request", "detail": "fecha_desde debe ser YYYY-MM-DD"}), 400

    if fecha_hasta:
        try:
            fecha_hasta_date = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
            query = query.filter(PmBitacoraORM.fecha <= fecha_hasta_date)
        except ValueError:
            return jsonify({"error": "Bad Request", "detail": "fecha_hasta debe ser YYYY-MM-DD"}), 400

    rows = (
        query.order_by(PmBitacoraORM.fecha.desc(), PmBitacoraORM.id.desc())
        .all()
    )

    return jsonify([
        _serializar_bitacora_pm_resumen(bitacora, inventario, sucursal, validacion)
        for bitacora, inventario, sucursal, validacion in rows
    ]), 200


# ────────────────────────────────────────────────────────────
# GET /preventivo/dashboard?sucursal_id=X&window_days=7
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
        return jsonify(
            {
                "error": "Bad Request",
                "detail": "window_days debe estar entre 1 y 90",
            }
        ), 400

    # ── 3) Scope check ──
    denied = _verificar_permiso_sucursal(claims, sucursal_id_int)
    if denied:
        return jsonify(denied[0]), denied[1]

    # ── 4) Subqueries ──
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

    ultima_bitacora_id_sq = (
        db.session.query(
            PmBitacoraORM.inventario_id,
            PmBitacoraORM.sucursal_id,
            func.max(PmBitacoraORM.id).label("ultima_bitacora_id"),
        )
        .filter(PmBitacoraORM.sucursal_id == sucursal_id_int)
        .group_by(PmBitacoraORM.inventario_id, PmBitacoraORM.sucursal_id)
        .subquery("ub")
    )

    # ── 5) Query principal ──
    rows = (
        db.session.query(
            PmPreventivoConfigORM,
            InventarioGeneral,
            Sucursal,
            ultima_fecha_sq.c.ultima_fecha,
            ultima_bitacora_id_sq.c.ultima_bitacora_id,
            PmValidacionORM.decision,
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
        .outerjoin(
            ultima_bitacora_id_sq,
            db.and_(
                ultima_bitacora_id_sq.c.inventario_id == PmPreventivoConfigORM.inventario_id,
                ultima_bitacora_id_sq.c.sucursal_id == PmPreventivoConfigORM.sucursal_id,
            ),
        )
        .outerjoin(
            PmValidacionORM,
            PmValidacionORM.bitacora_pm_id == ultima_bitacora_id_sq.c.ultima_bitacora_id,
        )
        .filter(
            PmPreventivoConfigORM.sucursal_id == sucursal_id_int,
            PmPreventivoConfigORM.activo.is_(True),
        )
        .all()
    )

    # ── 6) Clasificar ──
    hoy = date.today()
    atrasados = []
    hoy_list = []
    proximos = []

    for cfg, inv, suc, ultima_fecha, ultima_bitacora_id, decision_validacion in rows:
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

        if ultima_bitacora_id:
            estado_ejecucion = "CAPTURADO"
        else:
            estado_ejecucion = "SIN_CAPTURA"

        if not ultima_bitacora_id:
            estado_validacion = "SIN_VALIDACION"
        elif decision_validacion == "VALIDADO":
            estado_validacion = "VALIDADO"
        elif decision_validacion == "RECHAZADO":
            estado_validacion = "RECHAZADO"
        else:
            estado_validacion = "PENDIENTE_VALIDACION"

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
            "estado_ejecucion": estado_ejecucion,
            "estado_validacion": estado_validacion,
            "bitacora_pm_id": ultima_bitacora_id,
        }

        if estado == "ATRASADO":
            atrasados.append(item)
        elif estado == "HOY":
            hoy_list.append(item)
        elif estado == "PROXIMO":
            proximos.append(item)

    return jsonify(
        {
            "atrasados": atrasados,
            "hoy": hoy_list,
            "proximos": proximos,
        }
    ), 200