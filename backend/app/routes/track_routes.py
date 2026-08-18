#   backend\app\routes\track_routes.py


from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Any
from app.extensions import db
from app.models.user_model import UserORM
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.warehouse import TrackDailyMartORM
from app.warehouse.services.track_daily_version_service import (
    TrackDailyVersionServiceError,
    get_current_track_daily_version,
    get_latest_track_canonical_close_version,
    request_track_canonical_close,
)
from app.warehouse.services.track_daily_pipeline_service import (
    run_track_agregadoras_integration_for_date,
    run_track_daily_pipeline_for_date,
)
from app.warehouse.services.track_excel_export_service import (
    build_track_daily_mart_excel,
)
from app.warehouse.services.track_daily_query_version_service import (
    resolve_effective_track_daily_version,
)
from app.warehouse.services.track_source_agregadoras_daily_service import (
    resolve_exact_agregadoras_snapshot_status_for_date,
)


track_bp = Blueprint("track_bp", __name__)


ALLOWED_GENERATION_MODES = {
    "official_closed_day",
    "manual_preview",
}


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise ValueError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise ValueError(f"Valor inválido para {field_name!r}: {value!r}")

def _ensure_target_month(value: Any, *, field_name: str) -> tuple[int, int]:
    if not isinstance(value, str):
        raise ValueError(f"Valor inválido para {field_name!r}: {value!r}")

    raw_value = value.strip()

    try:
        parts = raw_value.split("-")
        year = int(parts[0])
        month = int(parts[1])
    except Exception as exc:
        raise ValueError(
            f"No se pudo convertir a YYYY-MM el campo {field_name!r}: {value!r}"
        ) from exc

    if month < 1 or month > 12:
        raise ValueError(
            f"Mes inválido para {field_name!r}: {value!r}"
        )

    return year, month


def _get_current_role() -> str:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return ""

    user = UserORM.get_by_id(user_id)
    if not user:
        return ""

    return str(getattr(user, "rol", "") or "").strip().upper()


def _require_track_admin_role() -> None:
    role = _get_current_role()

    if role not in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}:
        raise PermissionError("No autorizado para ejecutar procesos del Track.")


def _require_track_read_role() -> None:
    role = _get_current_role()

    if role not in {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "LECTOR_GLOBAL",
        "GERENTE",
        "GERENTE_REGIONAL",
        "SISTEMAS",
        "GERENCIA DEPORTIVA",
        "MARKETING",
        "TIENDA",
    }:
        raise PermissionError("No autorizado para consultar el Track.")


def _serialize_decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)

def _today_tijuana() -> date:
    return datetime.now(ZoneInfo("America/Tijuana")).date()

def _resolve_track_branch_history_rows(
    *,
    sucursal_canon: str,
    generation_mode: str,
    candidate_dates: list[date],
) -> list[TrackDailyMartORM]:
    resolved_rows: list[TrackDailyMartORM] = []

    for candidate_date in candidate_dates:
        resolved_version = resolve_effective_track_daily_version(
            track_date=candidate_date,
            generation_mode=generation_mode,
        )

        if resolved_version is None:
            continue

        row = TrackDailyMartORM.query.filter_by(
            track_daily_version_id=resolved_version.id,
            sucursal_canon=sucursal_canon,
        ).one_or_none()

        if row is not None:
            resolved_rows.append(row)

    return resolved_rows


def _serialize_track_canonical_close_version(
    version: Any,
) -> dict[str, Any] | None:
    if version is None:
        return None

    def _iso(value: Any) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "id": version.id,
        "track_date": _iso(version.track_date),
        "version_type": version.version_type,
        "status": version.status,
        "is_current": bool(version.is_current),
        "base_version_id": version.base_version_id,
        "replaces_version_id": version.replaces_version_id,
        "retry_count": int(version.retry_count or 0),
        "requested_by": version.requested_by,
        "trigger_source": version.trigger_source,
        "error_message": version.error_message,
        "generated_at_utc": _iso(version.generated_at_utc),
        "started_at_utc": _iso(version.started_at_utc),
        "finished_at_utc": _iso(version.finished_at_utc),
        "created_at": _iso(version.created_at),
        "updated_at": _iso(version.updated_at),
    }

def _serialize_track_daily_mart_row(row: TrackDailyMartORM) -> dict[str, Any]:
    return {
        "track_daily_version_id": row.track_daily_version_id,
        "track_date": row.track_date.isoformat(),
        "generation_mode": row.generation_mode,
        "sucursal_canon": row.sucursal_canon,
        "target_month": row.target_month.isoformat() if row.target_month else None,
        "m2_sin_circulaciones": _serialize_decimal(row.m2_sin_circulaciones),
        "usuarios_inicio_mes": row.usuarios_inicio_mes,
        "proyeccion_usuarios_cierre_mes": row.proyeccion_usuarios_cierre_mes,
        "meta_faycgo_mes": _serialize_decimal(row.meta_faycgo_mes),
        "meta_clientes_nuevos_mes": row.meta_clientes_nuevos_mes,
        "meta_reactivaciones_mes": row.meta_reactivaciones_mes,
        "meta_bajas_mes": row.meta_bajas_mes,
        "meta_nuevos_domiciliados_mes": row.meta_nuevos_domiciliados_mes,
        "meta_arpu_mes": _serialize_decimal(row.meta_arpu_mes),
        "meta_venta_tienda_mes": _serialize_decimal(row.meta_venta_tienda_mes),
        "venta_tienda_real_mtd": _serialize_decimal(row.venta_tienda_real_mtd),
        "usuarios_activos_actual": row.usuarios_activos_actual,
        "reactivaciones_real_mtd": row.reactivaciones_real_mtd,
        "bajas_reales_mtd": row.bajas_reales_mtd,
        "ingreso_real_base_mtd": _serialize_decimal(row.ingreso_real_base_mtd),
        "ingreso_real_agregadora_mtd": _serialize_decimal(row.ingreso_real_agregadora_mtd),        
        "ingreso_real_mtd": _serialize_decimal(row.ingreso_real_mtd),
        "clientes_nuevos_real_mtd": row.clientes_nuevos_real_mtd,
        "nuevos_domiciliados_real_mtd": row.nuevos_domiciliados_real_mtd,
        "source_business_date_desempeno": (
            row.source_business_date_desempeno.isoformat()
            if row.source_business_date_desempeno
            else None
        ),
        "source_business_date_ingresos": (
            row.source_business_date_ingresos.isoformat()
            if row.source_business_date_ingresos
            else None
        ),
        "source_business_date_agregadoras": (
            row.source_business_date_agregadoras.isoformat()
            if row.source_business_date_agregadoras
            else None
        ),
        "source_business_date_nuevos": (
            row.source_business_date_nuevos.isoformat()
            if row.source_business_date_nuevos
            else None
        ),
        "source_business_date_domiciliados": (
            row.source_business_date_domiciliados.isoformat()
            if row.source_business_date_domiciliados
            else None
        ),
        "source_business_date_tienda": (
            row.source_business_date_tienda.isoformat()
            if row.source_business_date_tienda
            else None
        ),
        "source_snapshot_id_desempeno": row.source_snapshot_id_desempeno,
        "source_snapshot_id_ingresos": row.source_snapshot_id_ingresos,
        "source_snapshot_id_nuevos": row.source_snapshot_id_nuevos,
        "source_snapshot_id_domiciliados": row.source_snapshot_id_domiciliados,
        "source_snapshot_id_tienda": row.source_snapshot_id_tienda,
    }


@track_bp.route("/run-daily-pipeline", methods=["POST"])
@jwt_required()
def run_track_daily_pipeline_endpoint():
    try:
        _require_track_admin_role()

        payload = request.get_json(silent=True) or {}

        track_date = _ensure_date(
            payload.get("track_date"),
            field_name="track_date",
        )

        generation_mode = str(
            payload.get("generation_mode") or "manual_preview"
        ).strip()

        if generation_mode not in ALLOWED_GENERATION_MODES:
            return jsonify(
                {
                    "status": "error",
                    "message": "generation_mode inválido.",
                    "allowed_generation_modes": sorted(ALLOWED_GENERATION_MODES),
                }
            ), 400
            
        today_local = _today_tijuana()

        if track_date < today_local:
            return jsonify(
                {
                    "status": "error",
                    "message": (
                        "No se puede generar Track para fechas pasadas desde este flujo. "
                        "Consulta la versión histórica cerrada."
                    ),
                    "track_date": track_date.isoformat(),
                    "today": today_local.isoformat(),
                    "generation_mode": generation_mode,
                }
            ), 400

        requested_by = str(payload.get("requested_by") or "api_manual_trigger").strip()
        trigger_source = str(payload.get("trigger_source") or "api_track_manual_run").strip()

        result = run_track_daily_pipeline_for_date(
            business_date=track_date,
            generation_mode=generation_mode,
            requested_by=requested_by,
            trigger_source=trigger_source,
        )

        return jsonify(
            {
                "status": "ok",
                "result": result,
            }
        ), 200

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except ValueError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la ejecución manual del pipeline del Track.",
                "detail": str(exc),
            }
        ), 500

@track_bp.route("/canonical-close-status", methods=["GET"])
@jwt_required()
def get_track_canonical_close_status_endpoint():
    """
    Devuelve el cierre current visible y el último intento de cierre
    canónico para una fecha histórica.
    """
    try:
        _require_track_admin_role()

        track_date = _ensure_date(
            request.args.get("track_date"),
            field_name="track_date",
        )

        today_local = _today_tijuana()

        if track_date >= today_local:
            return jsonify(
                {
                    "status": "error",
                    "message": (
                        "El estado de cierre canónico manual "
                        "solo aplica a fechas pasadas."
                    ),
                    "track_date": track_date.isoformat(),
                    "today": today_local.isoformat(),
                }
            ), 400

        current_close = get_current_track_daily_version(
            track_date=track_date,
            version_type="cierre_canonico",
        )

        latest_attempt = (
            get_latest_track_canonical_close_version(
                track_date=track_date,
            )
        )

        has_active_request = bool(
            latest_attempt is not None
            and not latest_attempt.is_current
            and latest_attempt.status in {"pending", "running"}
        )

        return jsonify(
            {
                "status": "ok",
                "track_date": track_date.isoformat(),
                "current_close": (
                    _serialize_track_canonical_close_version(
                        current_close
                    )
                ),
                "latest_attempt": (
                    _serialize_track_canonical_close_version(
                        latest_attempt
                    )
                ),
                "has_active_request": has_active_request,
                "can_request_close": not has_active_request,
            }
        ), 200

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except ValueError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la consulta del estado de "
                    "cierre canónico del Track."
                ),
                "detail": str(exc),
            }
        ), 500


@track_bp.route("/request-canonical-close", methods=["POST"])
@jwt_required()
def request_track_canonical_close_endpoint():
    """
    Registra una solicitud asíncrona de cierre canónico histórico.

    Este endpoint NO ejecuta Gasca, refresh de fuentes ni mart.
    El track-scheduler reclama posteriormente la solicitud pending.
    """
    try:
        _require_track_admin_role()

        payload = request.get_json(silent=True) or {}

        track_date = _ensure_date(
            payload.get("track_date"),
            field_name="track_date",
        )

        today_local = _today_tijuana()

        if track_date >= today_local:
            return jsonify(
                {
                    "status": "error",
                    "message": (
                        "El cierre canónico manual solo aplica "
                        "a fechas pasadas."
                    ),
                    "track_date": track_date.isoformat(),
                    "today": today_local.isoformat(),
                }
            ), 400

        agregadoras_readiness = (
            resolve_exact_agregadoras_snapshot_status_for_date(
                business_date=track_date,
            )
        )

        if not agregadoras_readiness.get("is_ready"):
            return jsonify(
                {
                    "status": "not_ready",
                    "message": (
                        "No existen agregadoras exactas para "
                        "la fecha seleccionada."
                    ),
                    "track_date": track_date.isoformat(),
                    "agregadoras_readiness": (
                        agregadoras_readiness
                    ),
                }
            ), 409

        jwt_identity = get_jwt_identity()
        requested_by = str(
            jwt_identity
            if jwt_identity is not None
            else ""
        ).strip()

        if not requested_by:
            return jsonify(
                {
                    "status": "error",
                    "message": (
                        "No se pudo resolver el usuario "
                        "solicitante desde el JWT."
                    ),
                }
            ), 401

        request_version = request_track_canonical_close(
            track_date=track_date,
            requested_by=requested_by,
            trigger_source="api_manual_canonical_close",
            auto_commit=True,
        )

        return jsonify(
            {
                "status": "accepted",
                "track_date": track_date.isoformat(),
                "request": {
                    "id": request_version.id,
                    "version_type": (
                        request_version.version_type
                    ),
                    "status": request_version.status,
                    "is_current": (
                        request_version.is_current
                    ),
                    "base_version_id": (
                        request_version.base_version_id
                    ),
                    "replaces_version_id": (
                        request_version.replaces_version_id
                    ),
                    "retry_count": (
                        request_version.retry_count
                    ),
                    "requested_by": (
                        request_version.requested_by
                    ),
                    "trigger_source": (
                        request_version.trigger_source
                    ),
                },
                "agregadoras_readiness": (
                    agregadoras_readiness
                ),
            }
        ), 202

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except ValueError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400

    except TrackDailyVersionServiceError as exc:
        return jsonify(
            {
                "status": "not_ready",
                "message": str(exc),
            }
        ), 409

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": (
                    "Falló la solicitud de cierre "
                    "canónico del Track."
                ),
                "detail": str(exc),
            }
        ), 500


@track_bp.route("/run-agregadoras-integration", methods=["POST"])
@jwt_required()
def run_track_agregadoras_integration_endpoint():
    try:
        _require_track_admin_role()

        payload = request.get_json(silent=True) or {}

        track_date = _ensure_date(
            payload.get("track_date"),
            field_name="track_date",
        )

        requested_by = str(
            payload.get("requested_by") or "api_agregadoras_integration"
        ).strip()
        trigger_source = str(
            payload.get("trigger_source") or "api_track_agregadoras_integration"
        ).strip()

        result = run_track_agregadoras_integration_for_date(
            business_date=track_date,
            requested_by=requested_by,
            trigger_source=trigger_source,
        )

        return jsonify(
            {
                "status": "ok",
                "result": result,
            }
        ), 200

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except ValueError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la integración manual de agregadoras del Track.",
                "detail": str(exc),
            }
        ), 500
@track_bp.route("/daily-mart", methods=["GET"])
@jwt_required()
def get_track_daily_mart_endpoint():
    try:
        _require_track_read_role()

        track_date = _ensure_date(
            request.args.get("track_date"),
            field_name="track_date",
        )

        generation_mode = str(
            request.args.get("generation_mode") or "manual_preview"
        ).strip()

        if generation_mode not in ALLOWED_GENERATION_MODES:
            return jsonify(
                {
                    "status": "error",
                    "message": "generation_mode inválido.",
                    "allowed_generation_modes": sorted(ALLOWED_GENERATION_MODES),
                }
            ), 400

        resolved_version = resolve_effective_track_daily_version(
            track_date=track_date,
            generation_mode=generation_mode,
        )

        if resolved_version is None:
            rows = []
        else:
            rows = (
                TrackDailyMartORM.query.filter_by(
                    track_daily_version_id=resolved_version.id,
                )
                .order_by(TrackDailyMartORM.sucursal_canon.asc())
                .all()
            )

        return jsonify(
            {
                "status": "ok",
                "track_date": track_date.isoformat(),
                "generation_mode": generation_mode,
                "resolved_version": (
                    {
                        "id": resolved_version.id,
                        "version_type": resolved_version.version_type,
                        "status": resolved_version.status,
                        "generated_at_utc": (
                            resolved_version.generated_at_utc.isoformat()
                            if resolved_version.generated_at_utc
                            else None
                        ),
                        "started_at_utc": (
                            resolved_version.started_at_utc.isoformat()
                            if resolved_version.started_at_utc
                            else None
                        ),
                        "finished_at_utc": (
                            resolved_version.finished_at_utc.isoformat()
                            if resolved_version.finished_at_utc
                            else None
                        ),
                    }
                    if resolved_version
                    else None
                ),
                "total_rows": len(rows),
                "rows": [_serialize_track_daily_mart_row(row) for row in rows],
            }
        ), 200

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except ValueError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta del Track daily mart.",
                "detail": str(exc),
            }
        ), 500
        
@track_bp.route("/daily-mart/export-xlsx", methods=["GET"])
@jwt_required()
def export_track_daily_mart_xlsx_endpoint():
    try:
        _require_track_read_role()

        track_date = _ensure_date(
            request.args.get("track_date"),
            field_name="track_date",
        )

        generation_mode = str(
            request.args.get("generation_mode") or "manual_preview"
        ).strip()

        if generation_mode not in ALLOWED_GENERATION_MODES:
            return jsonify(
                {
                    "status": "error",
                    "message": "generation_mode inválido.",
                    "allowed_generation_modes": sorted(ALLOWED_GENERATION_MODES),
                }
            ), 400

        resolved_version = resolve_effective_track_daily_version(
            track_date=track_date,
            generation_mode=generation_mode,
        )

        if resolved_version is None:
            return jsonify(
                {
                    "status": "error",
                    "message": "No hay versión disponible del Track para exportar.",
                    "track_date": track_date.isoformat(),
                    "generation_mode": generation_mode,
                }
            ), 404

        rows = (
            TrackDailyMartORM.query.filter_by(
                track_daily_version_id=resolved_version.id,
            )
            .order_by(TrackDailyMartORM.sucursal_canon.asc())
            .all()
        )

        if not rows:
            return jsonify(
                {
                    "status": "error",
                    "message": "La versión resuelta no tiene rows de mart para exportar.",
                    "track_date": track_date.isoformat(),
                    "generation_mode": generation_mode,
                    "track_daily_version_id": resolved_version.id,
                }
            ), 404

        excel_bytes = build_track_daily_mart_excel(
            track_date=track_date,
            generation_mode=generation_mode,
            resolved_version=resolved_version,
            rows=rows,
        )

        filename = f"Track_{track_date.isoformat()}_{generation_mode}.xlsx"

        return send_file(
            BytesIO(excel_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except ValueError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la exportación Excel del Track daily mart.",
                "detail": str(exc),
            }
        ), 500
        
@track_bp.route("/branch-history", methods=["GET"])
@jwt_required()
def get_track_branch_history_endpoint():
    try:
        _require_track_read_role()
        sucursal_canon = str(
            request.args.get("sucursal_canon") or ""
        ).strip().upper()

        if not sucursal_canon:
            return jsonify(
                {
                    "status": "error",
                    "message": "sucursal_canon es obligatorio.",
                }
            ), 400

        generation_mode = str(
            request.args.get("generation_mode") or "manual_preview"
        ).strip()

        if generation_mode not in ALLOWED_GENERATION_MODES:
            return jsonify(
                {
                    "status": "error",
                    "message": "generation_mode inválido.",
                    "allowed_generation_modes": sorted(ALLOWED_GENERATION_MODES),
                }
            ), 400

        raw_target_month = request.args.get("target_month")

        if raw_target_month:
            target_year, target_month = _ensure_target_month(
                raw_target_month,
                field_name="target_month",
            )

            candidate_dates = [
                row.track_date
                for row in (
                    db.session.query(TrackDailyMartORM.track_date)
                    .filter(TrackDailyMartORM.sucursal_canon == sucursal_canon)
                    .filter(TrackDailyMartORM.track_daily_version_id.isnot(None))
                    .filter(db.extract("year", TrackDailyMartORM.track_date) == target_year)
                    .filter(db.extract("month", TrackDailyMartORM.track_date) == target_month)
                    .distinct()
                    .order_by(TrackDailyMartORM.track_date.asc())
                    .all()
                )
            ]

            rows = _resolve_track_branch_history_rows(
                sucursal_canon=sucursal_canon,
                generation_mode=generation_mode,
                candidate_dates=candidate_dates,
            )

            serialized_rows = [
                _serialize_track_daily_mart_row(row)
                for row in rows
            ]

            return jsonify(
                {
                    "status": "ok",
                    "sucursal_canon": sucursal_canon,
                    "generation_mode": generation_mode,
                    "target_month": raw_target_month,
                    "total_rows": len(serialized_rows),
                    "rows": serialized_rows,
                }
            ), 200

        raw_days = request.args.get("days", "5")

        try:
            days = int(raw_days)
        except Exception:
            return jsonify(
                {
                    "status": "error",
                    "message": "days debe ser un entero.",
                }
            ), 400

        if days <= 0 or days > 31:
            return jsonify(
                {
                    "status": "error",
                    "message": "days debe estar entre 1 y 31.",
                }
            ), 400

        candidate_dates = [
            row.track_date
            for row in (
                db.session.query(TrackDailyMartORM.track_date)
                .filter(TrackDailyMartORM.sucursal_canon == sucursal_canon)
                .filter(TrackDailyMartORM.track_daily_version_id.isnot(None))
                .distinct()
                .order_by(TrackDailyMartORM.track_date.desc())
                .limit(120)
                .all()
            )
        ]

        rows = _resolve_track_branch_history_rows(
            sucursal_canon=sucursal_canon,
            generation_mode=generation_mode,
            candidate_dates=candidate_dates,
        )[:days]

        serialized_rows = [
            _serialize_track_daily_mart_row(row)
            for row in reversed(rows)
        ]

        return jsonify(
            {
                "status": "ok",
                "sucursal_canon": sucursal_canon,
                "generation_mode": generation_mode,
                "days_requested": days,
                "total_rows": len(serialized_rows),
                "rows": serialized_rows,
            }
        ), 200

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except ValueError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Error consultando historial de Track por sucursal.",
                "detail": str(exc),
            }
        ), 500
