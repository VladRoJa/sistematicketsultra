#backend\app\routes\pm_routes.py


from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, date, timedelta
from sqlalchemy import func
from calendar import monthrange

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
# HELPERS 
# ────────────────────────────────────────────────────────────
def _verificar_permiso_sucursal(claims, sucursal_id_int):
    """
    Valida que el token tenga acceso a la sucursal indicada.
    Retorna None si OK, o (response_dict, status_code) si denegado.
    """
    rol = (claims.get("rol") or "").strip().upper()

    if rol in _ADMIN_ROLES:
        return None

    if rol in {"MANTENIMIENTO", "SISTEMAS", "TECNICO"}:
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


def _crear_bitacora(data, claims, user_id):
    """
    Valida, verifica permisos e inserta una PmBitacoraORM.
    Retorna (bitacora, None) si OK, o (None, (response_dict, status_code)) si error.
    """
    inventario_id = data.get("inventario_id")
    sucursal_id = data.get("sucursal_id")
    fecha = data.get("fecha")  # "YYYY-MM-DD"
    resultado = data.get("resultado")  # "OK" | "FALLA" | "OBS"
    tipo_mantenimiento = data.get("tipo_mantenimiento")  # "CORRECTIVO" | "PREVENTIVO" | "ESTETICO" | "MEJORA"
    notas = data.get("notas") or ""
    checks = data.get("checks") or {}

    # 1) Validación de requeridos
    if not inventario_id or not sucursal_id or not fecha or not resultado or not tipo_mantenimiento:
        return None, (
            {
                "error": "Bad Request",
                "detail": "Campos requeridos: inventario_id, sucursal_id, fecha, resultado, tipo_mantenimiento",
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
        tipo_mantenimiento=tipo_mantenimiento,
        notas=notas,
        checks=checks,
    )
    db.session.add(bit)
    db.session.commit()

    return bit, None


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


def _crear_configuracion_pm(data, claims):
    inventario_id = data.get("inventario_id")
    sucursal_id = data.get("sucursal_id")
    frecuencia_dias = data.get("frecuencia_dias")
    fecha_base_programacion = data.get("fecha_base_programacion")

    activo = data.get("activo", True)

    if (
        not inventario_id
        or not sucursal_id
        or frecuencia_dias is None
        or fecha_base_programacion is None
    ):
        
        return None, (
            {
                "error": "Bad Request",
                "detail": "Campos requeridos: inventario_id, sucursal_id, frecuencia_dias, fecha_base_programacion",
            },
            400,
        )

    try:
        inventario_id_int = int(inventario_id)
        sucursal_id_int = int(sucursal_id)
        frecuencia_dias_int = int(frecuencia_dias)
    except (TypeError, ValueError):
        return None, (
            {
                "error": "Bad Request",
                "detail": "inventario_id, sucursal_id y frecuencia_dias deben ser enteros",
            },
            400,
        )

    semana_programada_mes_int = None
    
    if frecuencia_dias_int <= 0:
        return None, (
            {
                "error": "Bad Request",
                "detail": "frecuencia_dias debe ser mayor a 0",
            },
            400,
        )
    
    try:
        fecha_base_programacion_date = date.fromisoformat(fecha_base_programacion)
    except (TypeError, ValueError):
        return None, (
            {
                "error": "Bad Request",
                "detail": "fecha_base_programacion debe tener formato YYYY-MM-DD",
            },
            400,
        )
   

    denied = _verificar_permiso_sucursal(claims, sucursal_id_int)
    if denied:
        return None, denied

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

    existente = PmPreventivoConfigORM.query.filter_by(
        inventario_id=inventario_id_int,
        sucursal_id=sucursal_id_int,
    ).first()
    if existente:
        return None, (
            {
                "error": "Conflict",
                "detail": "Ya existe una configuración PM para ese equipo en esa sucursal",
            },
            409,
        )

    cfg = PmPreventivoConfigORM(
        inventario_id=inventario_id_int,
        sucursal_id=sucursal_id_int,
        frecuencia_dias=frecuencia_dias_int,
        fecha_base_programacion=fecha_base_programacion_date,
        activo=bool(activo),
    )
    db.session.add(cfg)
    db.session.commit()

    return cfg, None


def _actualizar_configuracion_pm(config_id, data, claims):
    try:
        config_id_int = int(config_id)
    except (TypeError, ValueError):
        return None, (
            {"error": "Bad Request", "detail": "config_id debe ser entero"},
            400,
        )

    cfg = db.session.get(PmPreventivoConfigORM, config_id_int)
    if not cfg:
        return None, (
            {"error": "Not Found", "detail": "La configuración PM no existe"},
            404,
        )

    denied = _verificar_permiso_sucursal(claims, cfg.sucursal_id)
    if denied:
        return None, denied

    frecuencia_dias = data.get("frecuencia_dias")
    activo = data.get("activo")
    fecha_base_programacion = data.get("fecha_base_programacion")

    if frecuencia_dias is None and activo is None and fecha_base_programacion is None:
        return None, (
            {
                "error": "Bad Request",
                "detail": "Debes enviar al menos frecuencia_dias, fecha_base_programacion o activo",
            },
            400,
        )

    if frecuencia_dias is not None:
        try:
            frecuencia_dias_int = int(frecuencia_dias)
        except (TypeError, ValueError):
            return None, (
                {"error": "Bad Request", "detail": "frecuencia_dias debe ser entero"},
                400,
            )

        if frecuencia_dias_int <= 0:
            return None, (
                {"error": "Bad Request", "detail": "frecuencia_dias debe ser mayor a 0"},
                400,
            )

        cfg.frecuencia_dias = frecuencia_dias_int
    if fecha_base_programacion is not None:
        try:
            fecha_base_programacion_date = date.fromisoformat(fecha_base_programacion)
        except (TypeError, ValueError):
            return None, (
                {
                    "error": "Bad Request",
                    "detail": "fecha_base_programacion debe tener formato YYYY-MM-DD",
                },
                400,
            )

        cfg.fecha_base_programacion = fecha_base_programacion_date
        
    if activo is not None:
        cfg.activo = bool(activo)

    db.session.commit()
    return cfg, None

def _serializar_bitacora_pm_detalle(bitacora):
    validacion = bitacora.pm_validacion

    return {
        "id": bitacora.id,
        "inventario_id": bitacora.inventario_id,
        "sucursal_id": bitacora.sucursal_id,
        "created_by_user_id": bitacora.created_by_user_id,
        "fecha": bitacora.fecha.isoformat() if bitacora.fecha else None,
        "resultado": bitacora.resultado,
        "tipo_mantenimiento": bitacora.tipo_mantenimiento,
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
    
def _serializar_pm_config_resumen(cfg, inventario, sucursal):
    return {
        "id": cfg.id,
        "inventario_id": cfg.inventario_id,
        "codigo_interno": inventario.codigo_interno,
        "nombre": inventario.nombre,
        "sucursal_id": cfg.sucursal_id,
        "sucursal": sucursal.sucursal,
        "frecuencia_dias": cfg.frecuencia_dias,
        "fecha_base_programacion": cfg.fecha_base_programacion.isoformat() if cfg.fecha_base_programacion else None,
        "activo": cfg.activo,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }

def _formatear_ddmm(fecha: date) -> str:
    return fecha.strftime("%d/%m")


def _primer_domingo_del_mes(anio: int, mes: int) -> date | None:
    _, ultimo_dia = monthrange(anio, mes)

    for dia in range(1, ultimo_dia + 1):
        fecha = date(anio, mes, dia)
        # weekday(): lunes=0 ... domingo=6
        if fecha.weekday() == 6:
            return fecha

    return None


def _inicio_anio_domingo(anio: int) -> date:
    primero_enero = date(anio, 1, 1)
    dias_hacia_atras = (primero_enero.weekday() + 1) % 7
    return primero_enero - timedelta(days=dias_hacia_atras)


def _calcular_semana_anio_domingo_sabado(fecha: date) -> int:
    inicio = _inicio_anio_domingo(fecha.year)
    diff_dias = (fecha - inicio).days
    return (diff_dias // 7) + 1


def _generar_semanas_visibles_mes(anio: int, mes: int):
    primer_domingo = _primer_domingo_del_mes(anio, mes)
    if not primer_domingo:
        return []

    semanas = []
    semana_programada_mes = 1
    domingo_actual = primer_domingo

    while domingo_actual.month == mes:
        sabado_actual = domingo_actual + timedelta(days=6)
        semana_anio = _calcular_semana_anio_domingo_sabado(domingo_actual)

        semanas.append({
            "anio": anio,
            "mes": mes,
            "semana_anio": semana_anio,
            "semana_programada_mes": semana_programada_mes,
            "fecha_inicio_iso": domingo_actual.isoformat(),
            "fecha_fin_iso": sabado_actual.isoformat(),
            "fecha_inicio_label": _formatear_ddmm(domingo_actual),
            "fecha_fin_label": _formatear_ddmm(sabado_actual),
            "label": f"Semana {semana_anio} — {_formatear_ddmm(domingo_actual)} al {_formatear_ddmm(sabado_actual)}",
        })

        domingo_actual = domingo_actual + timedelta(days=7)
        semana_programada_mes += 1

    return semanas

def _generar_fechas_programadas_en_rango(
    fecha_base: date | None,
    frecuencia_dias: int,
    fecha_inicio: date,
    fecha_fin: date,
):
    if fecha_base is None or frecuencia_dias <= 0:
        return []

    fechas = []
    fecha_actual = fecha_base

    while fecha_actual < fecha_inicio:
        fecha_actual = fecha_actual + timedelta(days=frecuencia_dias)

    while fecha_actual <= fecha_fin:
        fechas.append(fecha_actual)
        fecha_actual = fecha_actual + timedelta(days=frecuencia_dias)

    return fechas

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
    
    department_id = claims.get("department_id")
    rol = (claims.get("rol") or "").strip().upper()

    if department_id == 1 or rol in {"MANTENIMIENTO", "SR_MANTENIMIENTO", "AUX_MANTENIMIENTO"}:
        query = query.filter(db.func.upper(InventarioGeneral.tipo) == "APARATOS")
    elif department_id == 7 or rol in {"SISTEMAS", "TECNICO"}:
        query = query.filter(db.func.upper(InventarioGeneral.tipo) == "DISPOSITIVOS")

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
# GET /configuraciones?sucursal_id=X
# ────────────────────────────────────────────────────────────

@pm_bp.route("/configuraciones", methods=["GET"])
@jwt_required()
def pm_listar_configuraciones():
    claims = get_jwt() or {}
    sucursal_id = request.args.get("sucursal_id", type=int)

    query = (
        db.session.query(
            PmPreventivoConfigORM,
            InventarioGeneral,
            Sucursal,
        )
        .join(
            InventarioGeneral,
            InventarioGeneral.id == PmPreventivoConfigORM.inventario_id,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id == PmPreventivoConfigORM.sucursal_id,
        )
    )
    
    department_id = claims.get("department_id")
    rol = (claims.get("rol") or "").strip().upper()

    if department_id == 1 or rol in {"MANTENIMIENTO", "SR_MANTENIMIENTO", "AUX_MANTENIMIENTO"}:
        query = query.filter(db.func.upper(InventarioGeneral.tipo) == "APARATOS")
    elif department_id == 7 or rol in {"SISTEMAS", "TECNICO"}:
        query = query.filter(db.func.upper(InventarioGeneral.tipo) == "DISPOSITIVOS")

    if sucursal_id:
        denied = _verificar_permiso_sucursal(claims, sucursal_id)
        if denied:
            return jsonify(denied[0]), denied[1]

        query = query.filter(PmPreventivoConfigORM.sucursal_id == sucursal_id)
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

                query = query.filter(PmPreventivoConfigORM.sucursal_id == user_sucursal)
            else:
                allowed = claims.get("sucursales_ids") or []
                try:
                    allowed = [int(x) for x in allowed]
                except Exception:
                    allowed = []

                if not allowed:
                    return jsonify({"error": "Forbidden", "detail": "No tienes acceso a sucursales"}), 403

                query = query.filter(PmPreventivoConfigORM.sucursal_id.in_(allowed))

    rows = (
        query.order_by(
            Sucursal.sucursal.asc(),
            InventarioGeneral.nombre.asc(),
            PmPreventivoConfigORM.id.asc(),
        )
        .all()
    )

    return jsonify([
        _serializar_pm_config_resumen(cfg, inventario, sucursal)
        for cfg, inventario, sucursal in rows
    ]), 200

# ────────────────────────────────────────────────────────────
# POST /configuraciones
# ────────────────────────────────────────────────────────────

@pm_bp.route("/configuraciones", methods=["POST"])
@jwt_required()
def pm_crear_configuracion():
    data = request.get_json(silent=True) or {}
    claims = get_jwt() or {}

    cfg, err = _crear_configuracion_pm(data, claims)
    if err:
        return jsonify(err[0]), err[1]

    inventario = db.session.get(InventarioGeneral, cfg.inventario_id)
    sucursal = db.session.get(Sucursal, cfg.sucursal_id)

    return jsonify(
        _serializar_pm_config_resumen(cfg, inventario, sucursal)
    ), 201

# ────────────────────────────────────────────────────────────
# PUT /configuraciones/<config_id>
# ────────────────────────────────────────────────────────────

@pm_bp.route("/configuraciones/<int:config_id>", methods=["PUT"])
@jwt_required()
def pm_actualizar_configuracion(config_id):
    data = request.get_json(silent=True) or {}
    claims = get_jwt() or {}

    cfg, err = _actualizar_configuracion_pm(config_id, data, claims)
    if err:
        return jsonify(err[0]), err[1]

    inventario = db.session.get(InventarioGeneral, cfg.inventario_id)
    sucursal = db.session.get(Sucursal, cfg.sucursal_id)

    return jsonify(
        _serializar_pm_config_resumen(cfg, inventario, sucursal)
    ), 200


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
    query = (
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
    )

    rol = (claims.get("rol") or "").strip().upper()
    department_id = claims.get("department_id")

    if department_id == 1 or rol in {"MANTENIMIENTO", "SR_MANTENIMIENTO", "AUX_MANTENIMIENTO"}:
        query = query.filter(db.func.upper(InventarioGeneral.tipo) == "APARATOS")
    elif department_id == 7 or rol in {"SISTEMAS", "TECNICO"}:
        query = query.filter(db.func.upper(InventarioGeneral.tipo) == "DISPOSITIVOS")

    rows = query.all()
    

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
    
    
# ────────────────────────────────────────────────────────────
# GET /calendario?anio=X&mes=Y&sucursales_ids=1,2,3
# ──────────────────────────────────────────────────────────── 
    
    
@pm_bp.route("/calendario",methods=["GET"])
@jwt_required()
def pm_calendario():
    claims = get_jwt() or {}

    anio = request.args.get("anio", type=int)
    mes = request.args.get("mes", type=int)
    semana_anio = request.args.get("semana_anio", type=int)
    sucursales_ids = request.args.getlist("sucursales_ids", type=int)

    if not anio or not mes:
        return jsonify({
            "error": "Bad Request",
            "detail": "anio y mes son requeridos",
        }), 400

    if mes < 1 or mes > 12:
        return jsonify({
            "error": "Bad Request",
            "detail": "mes debe estar entre 1 y 12",
        }), 400

    semanas = _generar_semanas_visibles_mes(anio, mes)

    if not semanas:
        return jsonify({
            "anio": anio,
            "mes": mes,
            "semanas": [],
            "sucursales": [],
            "detalle_semana_seleccionada": {
                "semana_anio": None,
                "semana_programada_mes": None,
                "fecha_inicio_iso": None,
                "fecha_fin_iso": None,
                "fecha_inicio_label": None,
                "fecha_fin_label": None,
                "label": None,
                "items": [],
            },
        }), 200

    query = (
        db.session.query(
            PmPreventivoConfigORM,
            InventarioGeneral,
            Sucursal,
        )
        .join(
            InventarioGeneral,
            InventarioGeneral.id == PmPreventivoConfigORM.inventario_id,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id == PmPreventivoConfigORM.sucursal_id,
        )
        .filter(PmPreventivoConfigORM.activo.is_(True))
    )

    department_id = claims.get("department_id")
    rol = (claims.get("rol") or "").strip().upper()

    if department_id == 1 or rol in {"MANTENIMIENTO", "SR_MANTENIMIENTO", "AUX_MANTENIMIENTO"}:
        query = query.filter(db.func.upper(InventarioGeneral.tipo) == "APARATOS")
    elif department_id == 7 or rol in {"SISTEMAS", "TECNICO"}:
        query = query.filter(db.func.upper(InventarioGeneral.tipo) == "DISPOSITIVOS")

    if sucursales_ids:
        for sucursal_id in sucursales_ids:
            denied = _verificar_permiso_sucursal(claims, sucursal_id)
            if denied:
                return jsonify(denied[0]), denied[1]

        query = query.filter(PmPreventivoConfigORM.sucursal_id.in_(sucursales_ids))
    else:
        rol = (claims.get("rol") or "").strip().upper()

        if rol not in _ADMIN_ROLES and rol not in {"MANTENIMIENTO", "SISTEMAS", "TECNICO"}:
            if rol == "AUX_MANTENIMIENTO":
                user_sucursal = claims.get("sucursal_id")
                try:
                    user_sucursal = int(user_sucursal) if user_sucursal is not None else None
                except Exception:
                    user_sucursal = None

                if not user_sucursal:
                    return jsonify({"error": "Forbidden", "detail": "No tienes acceso a sucursales"}), 403

                query = query.filter(PmPreventivoConfigORM.sucursal_id == user_sucursal)
            else:
                allowed = claims.get("sucursales_ids") or []
                try:
                    allowed = [int(x) for x in allowed]
                except Exception:
                    allowed = []

                if not allowed:
                    return jsonify({"error": "Forbidden", "detail": "No tienes acceso a sucursales"}), 403

                query = query.filter(PmPreventivoConfigORM.sucursal_id.in_(allowed))

    rows = query.all()

    sucursales_map = {}

    for cfg, inventario, sucursal in rows:
        key = sucursal.sucursal_id

        if key not in sucursales_map:
            sucursales_map[key] = {
                "sucursal_id": sucursal.sucursal_id,
                "sucursal": sucursal.sucursal,
                "celdas": [],
            }


    for sucursal_id, sucursal_row in sucursales_map.items():
        configs_sucursal = [
            cfg for cfg, inv, suc in rows
            if suc.sucursal_id == sucursal_id
        ]

        celdas = []

        for semana in semanas:
            fecha_inicio_semana = date.fromisoformat(semana["fecha_inicio_iso"])
            fecha_fin_semana = date.fromisoformat(semana["fecha_fin_iso"])

            total_programados = 0

            for cfg in configs_sucursal:
                fechas_programadas = _generar_fechas_programadas_en_rango(
                    cfg.fecha_base_programacion,
                    cfg.frecuencia_dias,
                    fecha_inicio_semana,
                    fecha_fin_semana,
                )

                total_programados += len(fechas_programadas)

            celdas.append({
                "sucursal_id": sucursal_row["sucursal_id"],
                "sucursal": sucursal_row["sucursal"],
                "anio": anio,
                "mes": mes,
                "semana_anio": semana["semana_anio"],
                "semana_programada_mes": semana["semana_programada_mes"],
                "fecha_inicio_iso": semana["fecha_inicio_iso"],
                "fecha_fin_iso": semana["fecha_fin_iso"],
                "fecha_inicio_label": semana["fecha_inicio_label"],
                "fecha_fin_label": semana["fecha_fin_label"],
                "label_semana": semana["label"],
                "total_programados": total_programados,
                "total_capturados": 0,
                "total_validados": 0,
                "total_rechazados": 0,
                "total_atrasados": 0,
                "total_sin_bitacora": total_programados,
                "estado_resumen": "SIN_PROGRAMACION" if total_programados == 0 else "PROGRAMADO",
            })

        sucursal_row["celdas"] = celdas

    semana_detalle = None

    if semana_anio is not None:
        semana_detalle = next((s for s in semanas if s["semana_anio"] == semana_anio), None)

    if semana_detalle is None:
        semana_detalle = semanas[0] if semanas else None

    detalle_items = []

    if semana_detalle is not None:
        fecha_inicio_detalle = date.fromisoformat(semana_detalle["fecha_inicio_iso"])
        fecha_fin_detalle = date.fromisoformat(semana_detalle["fecha_fin_iso"])

        for cfg, inventario, sucursal in rows:
            fechas_programadas = _generar_fechas_programadas_en_rango(
                cfg.fecha_base_programacion,
                cfg.frecuencia_dias,
                fecha_inicio_detalle,
                fecha_fin_detalle,
            )

            if not fechas_programadas:
                continue

            for fecha_programada in fechas_programadas:
                detalle_items.append({
                    "configuracion_pm_id": cfg.id,
                    "sucursal_id": sucursal.sucursal_id,
                    "sucursal": sucursal.sucursal,
                    "inventario_id": inventario.id,
                    "codigo_interno": inventario.codigo_interno,
                    "nombre": inventario.nombre,
                    "frecuencia_dias": cfg.frecuencia_dias,
                    "fecha_base_programacion": cfg.fecha_base_programacion.isoformat() if cfg.fecha_base_programacion else None,
                    "fecha_programada": fecha_programada.isoformat(),
                    "dia_semana": (fecha_programada.weekday() + 1) % 7,
                    "estado_operativo": "PROGRAMADO",
                })



    detalle_semana = {
        "semana_anio": semana_detalle["semana_anio"] if semana_detalle else None,
        "semana_programada_mes": semana_detalle["semana_programada_mes"] if semana_detalle else None,
        "fecha_inicio_iso": semana_detalle["fecha_inicio_iso"] if semana_detalle else None,
        "fecha_fin_iso": semana_detalle["fecha_fin_iso"] if semana_detalle else None,
        "fecha_inicio_label": semana_detalle["fecha_inicio_label"] if semana_detalle else None,
        "fecha_fin_label": semana_detalle["fecha_fin_label"] if semana_detalle else None,
        "label": semana_detalle["label"] if semana_detalle else None,
        "items": detalle_items,
    }

    return jsonify({
        "anio": anio,
        "mes": mes,
        "semanas": semanas,
        "sucursales": list(sucursales_map.values()),
        "detalle_semana_seleccionada": detalle_semana,
    }), 200
    
    
    