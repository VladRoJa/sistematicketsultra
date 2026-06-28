from __future__ import annotations

import csv
import os
import io
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.rpa import GascaSmsRequestORM
from app.models.user_model import UserORM
from app.rpa.services.gasca_sms_request_service import (
    GascaSmsRequestMotivo,
    create_and_process_gasca_sms_request,
)


rpa_gasca_sms_bp = Blueprint("rpa_gasca_sms", __name__)

_RPA_GASCA_SMS_GLOBAL_ROLES = {
    "ADMIN",
    "ADMINISTRADOR",
    "SUPER_ADMIN",
    "SISTEMAS",
}

_RPA_GASCA_SMS_ALLOWED_ROLES = _RPA_GASCA_SMS_GLOBAL_ROLES | {
    "GERENTE",
    "GERENTE_REGIONAL",
}


def _role_norm(user: UserORM | None) -> str:
    return str(getattr(user, "rol", "") or "").strip().upper()


def _is_global_user(user: UserORM | None) -> bool:
    return _role_norm(user) in _RPA_GASCA_SMS_GLOBAL_ROLES


def _get_current_user() -> UserORM | None:
    raw_user_id = get_jwt_identity()

    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    return UserORM.get_by_id(user_id)


def _normalizar_sucursales_ids(raw_value) -> list[int]:
    if raw_value is None:
        return []

    if not isinstance(raw_value, (list, tuple, set)):
        return []

    normalized: list[int] = []
    for item in raw_value:
        try:
            normalized.append(int(item))
        except (TypeError, ValueError):
            continue

    return sorted(set(normalized))


def _allowed_sucursales_for_user(user: UserORM | None) -> list[int]:
    if not user:
        return []

    allowed = _normalizar_sucursales_ids(getattr(user, "sucursales_ids", []))

    primary_sucursal_id = getattr(user, "sucursal_id", None)
    try:
        primary_sucursal_id = int(primary_sucursal_id) if primary_sucursal_id is not None else None
    except (TypeError, ValueError):
        primary_sucursal_id = None

    if primary_sucursal_id is not None:
        allowed.append(primary_sucursal_id)

    return sorted(set(allowed))


def _parse_optional_int(value, field_name: str):
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} inválido.")


def _parse_optional_date(value, field_name: str) -> date | None:
    if value in (None, ""):
        return None

    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} inválido. Formato esperado: YYYY-MM-DD.")


def _suite_timezone() -> ZoneInfo:
    timezone_name = (
        os.getenv("SUITE_TIMEZONE")
        or os.getenv("APP_TIMEZONE")
        or os.getenv("TZ")
        or "America/Tijuana"
    )

    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("America/Tijuana")


def _suite_local_today() -> date:
    return datetime.now(_suite_timezone()).date()


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=_suite_timezone())


def _exclusive_next_day(value: date) -> datetime:
    return datetime.combine(value + timedelta(days=1), time.min, tzinfo=_suite_timezone())


def _resolve_date_range(args) -> tuple[datetime | None, datetime | None, str]:
    preset = (args.get("date_preset") or "today").strip().lower()

    # Soportar alias simples por si el frontend manda period como Nube.
    if args.get("period") and not args.get("date_preset"):
        preset = str(args.get("period") or "today").strip().lower()

    today_value = _suite_local_today()

    if preset in {"all", "todo"}:
        return None, None, "all"

    if preset == "yesterday":
        target = today_value - timedelta(days=1)
        return _start_of_day(target), _exclusive_next_day(target), "yesterday"

    if preset in {"last_7_days", "last7", "7d"}:
        start = today_value - timedelta(days=6)
        return _start_of_day(start), _exclusive_next_day(today_value), "last_7_days"

    if preset in {"month", "this_month"}:
        start = today_value.replace(day=1)
        return _start_of_day(start), _exclusive_next_day(today_value), "month"

    if preset == "custom":
        date_from = _parse_optional_date(args.get("date_from"), "date_from")
        date_to = _parse_optional_date(args.get("date_to"), "date_to")

        if not date_from or not date_to:
            raise ValueError("date_from y date_to son obligatorios para date_preset=custom.")

        if date_from > date_to:
            raise ValueError("date_from no puede ser mayor que date_to.")

        return _start_of_day(date_from), _exclusive_next_day(date_to), "custom"

    # Default operativo: hoy.
    return _start_of_day(today_value), _exclusive_next_day(today_value), "today"


def _pin_filter_candidates(pin_raw: str) -> list[str]:
    digits = "".join(
        char for char in str(pin_raw or "").strip()
        if char.isdigit()
    )

    if not digits:
        return []

    candidates = [
        digits,
        digits.lstrip("0") or "0",
        digits.zfill(5),
    ]

    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)

    return unique


def _parse_page_args(args) -> tuple[int, int]:
    page = _parse_optional_int(args.get("page"), "page") or 1

    raw_page_size = (
        args.get("page_size")
        or args.get("per_page")
        or args.get("limit")
    )
    page_size = _parse_optional_int(raw_page_size, "page_size") or 25

    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    return page, page_size


def _require_module_access(user: UserORM | None):
    if not user:
        return jsonify({"error": "Unauthorized", "detail": "Usuario no encontrado."}), 401

    role = _role_norm(user)
    if role not in _RPA_GASCA_SMS_ALLOWED_ROLES:
        return jsonify({"error": "Forbidden", "detail": "No tienes acceso a este módulo."}), 403

    return None


def _require_sucursal_access(user: UserORM | None, sucursal_id: int | None):
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    if _is_global_user(user):
        return None

    if sucursal_id is None:
        return jsonify({
            "error": "Bad Request",
            "detail": "sucursal_id es obligatorio para usuarios con alcance por sucursal.",
        }), 400

    allowed_sucursales = _allowed_sucursales_for_user(user)
    if sucursal_id not in allowed_sucursales:
        return jsonify({"error": "Forbidden", "detail": "No tienes acceso a esta sucursal."}), 403

    return None


def _request_visible_for_user(user: UserORM | None, item: GascaSmsRequestORM) -> bool:
    if not user:
        return False

    if _is_global_user(user):
        return True

    if item.requested_by_user_id == user.id:
        return True

    if item.sucursal_id is None:
        return False

    return item.sucursal_id in _allowed_sucursales_for_user(user)


def _apply_gasca_sms_request_filters(user: UserORM, args):
    date_start, date_end, date_preset = _resolve_date_range(args)

    status = (args.get("status") or "").strip()
    pin = (args.get("pin") or "").strip()
    gasca_sucursal = (args.get("gasca_sucursal") or "").strip()
    sucursal_id = _parse_optional_int(args.get("sucursal_id"), "sucursal_id")

    query = GascaSmsRequestORM.query

    if not _is_global_user(user):
        allowed_sucursales = _allowed_sucursales_for_user(user)
        query = query.filter(GascaSmsRequestORM.sucursal_id.in_(allowed_sucursales or [-1]))

    if sucursal_id is not None:
        forbidden = _require_sucursal_access(user, sucursal_id)
        if forbidden:
            return None, date_preset, forbidden

        query = query.filter(GascaSmsRequestORM.sucursal_id == sucursal_id)

    if date_start is not None:
        query = query.filter(GascaSmsRequestORM.created_at >= date_start)

    if date_end is not None:
        query = query.filter(GascaSmsRequestORM.created_at < date_end)

    if status and status.upper() != "ALL":
        query = query.filter(GascaSmsRequestORM.status == status)

    if pin:
        candidates = _pin_filter_candidates(pin)
        if candidates:
            query = query.filter(GascaSmsRequestORM.pin_normalized.in_(candidates))

    if gasca_sucursal:
        query = query.filter(
            GascaSmsRequestORM.gasca_sucursal.ilike(f"%{gasca_sucursal}%")
        )

    return query, date_preset, None


def _csv_safe(value) -> str:
    if value is None:
        return ""

    return str(value)


def _gasca_sms_export_filename(date_preset: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_preset = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in str(date_preset or "export")
    )
    return f"gasca_sms_{safe_preset}_{stamp}.csv"


@rpa_gasca_sms_bp.route("/catalogs", methods=["GET"])
@jwt_required()
def gasca_sms_catalogs():
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    return jsonify({
        "motivos": list(GascaSmsRequestMotivo.ALL),
        "global_access": _is_global_user(user),
        "allowed_sucursales_ids": None if _is_global_user(user) else _allowed_sucursales_for_user(user),
    }), 200


@rpa_gasca_sms_bp.route("/requests", methods=["POST"])
@jwt_required()
def create_gasca_sms_request_route():
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    data = request.get_json(silent=True) or {}

    try:
        pin_raw = str(data.get("pin") or data.get("pin_raw") or "").strip()
        phone_raw = str(data.get("telefono") or data.get("phone") or data.get("phone_raw") or "").strip()
        motivo = str(data.get("motivo") or "").strip()
        motivo_detalle = str(data.get("motivo_detalle") or "").strip() or None

        requested_sucursal_id = _parse_optional_int(data.get("sucursal_id"), "sucursal_id")
        if requested_sucursal_id is None:
            requested_sucursal_id = getattr(user, "sucursal_id", None)
            requested_sucursal_id = int(requested_sucursal_id) if requested_sucursal_id is not None else None

        forbidden = _require_sucursal_access(user, requested_sucursal_id)
        if forbidden:
            return forbidden

        item = create_and_process_gasca_sms_request(
            pin_raw=pin_raw,
            phone_raw=phone_raw,
            motivo=motivo,
            motivo_detalle=motivo_detalle,
            requested_by_user_id=user.id,
            sucursal_id=requested_sucursal_id,
        )

        return jsonify({
            "request": item.to_public_dict(),
            "message": item.user_message,
        }), 201

    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": "Bad Request", "detail": str(exc)}), 400

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Error creando solicitud Gasca SMS")
        return jsonify({
            "error": "Internal Server Error",
            "detail": "No se pudo procesar la solicitud Gasca SMS.",
        }), 500


@rpa_gasca_sms_bp.route("/requests", methods=["GET"])
@jwt_required()
def list_gasca_sms_requests_route():
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    try:
        page, page_size = _parse_page_args(request.args)
        date_start, date_end, date_preset = _resolve_date_range(request.args)

        status = (request.args.get("status") or "").strip()
        pin = (request.args.get("pin") or "").strip()
        gasca_sucursal = (request.args.get("gasca_sucursal") or "").strip()
        sucursal_id = _parse_optional_int(request.args.get("sucursal_id"), "sucursal_id")

        query = GascaSmsRequestORM.query

        if not _is_global_user(user):
            allowed_sucursales = _allowed_sucursales_for_user(user)
            query = query.filter(GascaSmsRequestORM.sucursal_id.in_(allowed_sucursales or [-1]))

        if sucursal_id is not None:
            forbidden = _require_sucursal_access(user, sucursal_id)
            if forbidden:
                return forbidden
            query = query.filter(GascaSmsRequestORM.sucursal_id == sucursal_id)

        if date_start is not None:
            query = query.filter(GascaSmsRequestORM.created_at >= date_start)

        if date_end is not None:
            query = query.filter(GascaSmsRequestORM.created_at < date_end)

        if status and status.upper() != "ALL":
            query = query.filter(GascaSmsRequestORM.status == status)

        if pin:
            candidates = _pin_filter_candidates(pin)
            if candidates:
                query = query.filter(GascaSmsRequestORM.pin_normalized.in_(candidates))

        if gasca_sucursal:
            query = query.filter(
                GascaSmsRequestORM.gasca_sucursal.ilike(f"%{gasca_sucursal}%")
            )

        total = query.count()
        total_pages = (total + page_size - 1) // page_size if total else 0

        if total_pages and page > total_pages:
            page = total_pages

        offset = (page - 1) * page_size

        items = (
            query
            .order_by(GascaSmsRequestORM.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return jsonify({
            "items": [item.to_public_dict() for item in items],
            "count": len(items),
            "limit": page_size,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "date_preset": date_preset,
        }), 200

    except ValueError as exc:
        return jsonify({"error": "Bad Request", "detail": str(exc)}), 400


@rpa_gasca_sms_bp.route("/requests/export", methods=["GET"])
@jwt_required()
def export_gasca_sms_requests_route():
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    try:
        query, date_preset, forbidden = _apply_gasca_sms_request_filters(user, request.args)
        if forbidden:
            return forbidden

        # Límite defensivo para evitar exportaciones accidentales enormes.
        export_limit = _parse_optional_int(request.args.get("export_limit"), "export_limit") or 5000
        export_limit = max(1, min(export_limit, 20000))

        items = (
            query
            .order_by(GascaSmsRequestORM.created_at.desc())
            .limit(export_limit)
            .all()
        )

        output = io.StringIO()
        output.write("\ufeff")

        writer = csv.writer(output)
        writer.writerow([
            "ID",
            "Fecha solicitud",
            "PIN",
            "Telefono capturado",
            "Motivo",
            "Detalle motivo",
            "Estado",
            "Mensaje",
            "Sucursal Suite ID",
            "Usuario ID",
            "Nombre Gasca",
            "Telefono Gasca",
            "Codigo Gasca",
            "Generado Gasca",
            "Utilizado Gasca",
            "Sucursal Gasca",
            "Proveedor SMS",
            "Intentos",
            "Procesado",
            "Enviado",
        ])

        for item in items:
            writer.writerow([
                item.id,
                _csv_safe(item.created_at.isoformat() if item.created_at else ""),
                _csv_safe(item.pin_normalized),
                _csv_safe(item.requested_phone_masked),
                _csv_safe(item.motivo),
                _csv_safe(item.motivo_detalle),
                _csv_safe(item.status),
                _csv_safe(item.user_message),
                _csv_safe(item.sucursal_id),
                _csv_safe(item.requested_by_user_id),
                _csv_safe(item.gasca_nombre_masked),
                _csv_safe(item.gasca_phone_masked),
                _csv_safe(item.gasca_code_masked),
                _csv_safe(item.gasca_generated_raw),
                _csv_safe(item.gasca_used_raw),
                _csv_safe(item.gasca_sucursal),
                _csv_safe(item.sms_provider),
                _csv_safe(item.attempt_count),
                _csv_safe(item.processed_at.isoformat() if item.processed_at else ""),
                _csv_safe(item.sent_at.isoformat() if item.sent_at else ""),
            ])

        filename = _gasca_sms_export_filename(date_preset)

        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Exported-Rows": str(len(items)),
            },
        )

    except ValueError as exc:
        return jsonify({"error": "Bad Request", "detail": str(exc)}), 400


@rpa_gasca_sms_bp.route("/requests/<int:request_id>", methods=["GET"])
@jwt_required()
def get_gasca_sms_request_route(request_id: int):
    user = _get_current_user()
    forbidden = _require_module_access(user)
    if forbidden:
        return forbidden

    item = GascaSmsRequestORM.query.get(request_id)
    if not item:
        return jsonify({"error": "Not Found", "detail": "Solicitud no encontrada."}), 404

    if not _request_visible_for_user(user, item):
        return jsonify({"error": "Forbidden", "detail": "No tienes acceso a esta solicitud."}), 403

    return jsonify({"request": item.to_public_dict()}), 200
