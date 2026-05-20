#   backend\app\routes\track_routes.py


from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Any
from app.extensions import db
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt, jwt_required

from app.models.warehouse import TrackDailyMartORM
from app.warehouse.services.track_daily_version_service import (
    get_current_track_daily_version,
)
from app.warehouse.services.track_daily_pipeline_service import (
    run_track_agregadoras_integration_for_date,
    run_track_daily_pipeline_for_date,
)
from app.warehouse.services.track_excel_export_service import (
    build_track_daily_mart_excel,
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
    claims = get_jwt()
    return str(claims.get("rol") or "").strip().upper()


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
    }:
        raise PermissionError("No autorizado para consultar el Track.")


def _serialize_decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)

def _today_tijuana() -> date:
    return datetime.now(ZoneInfo("America/Tijuana")).date()

def _resolve_track_daily_version_type_candidates(
    *,
    generation_mode: str,
) -> list[str]:
    if generation_mode == "manual_preview":
        return ["preview_operativo"]

    if generation_mode == "official_closed_day":
        return [
            "cierre_canonico",
            "base_nocturna_canonica",
        ]

    raise ValueError(f"generation_mode inválido: {generation_mode!r}")

def _track_daily_version_has_mart_rows(*, version_id: int) -> bool:
    return (
        db.session.query(TrackDailyMartORM.id)
        .filter(TrackDailyMartORM.track_daily_version_id == version_id)
        .first()
        is not None
    )


def _resolve_replaced_track_daily_version_with_rows(version: Any):
    if version is None or not version.replaces_version_id:
        return None

    previous_version = db.session.get(
        type(version),
        version.replaces_version_id,
    )

    if previous_version is None:
        return None

    if previous_version.track_date != version.track_date:
        return None

    if previous_version.version_type != version.version_type:
        return None

    if previous_version.status not in {"success", "replaced"}:
        return None

    if not _track_daily_version_has_mart_rows(
        version_id=previous_version.id,
    ):
        return None

    return previous_version


def _resolve_current_track_daily_version_for_query(
    *,
    track_date: date,
    generation_mode: str,
):
    for version_type in _resolve_track_daily_version_type_candidates(
        generation_mode=generation_mode,
    ):
        version = get_current_track_daily_version(
            track_date=track_date,
            version_type=version_type,
        )

        if version is None:
            continue

        if (
            version.status == "success"
            and _track_daily_version_has_mart_rows(version_id=version.id)
        ):
            return version

        fallback_version = _resolve_replaced_track_daily_version_with_rows(
            version,
        )

        if fallback_version is not None:
            return fallback_version

    return None

def _get_track_local_today() -> date:
    return datetime.now(ZoneInfo("America/Tijuana")).date()


def _resolve_track_daily_history_version_type_candidates(
    *,
    track_date: date,
    generation_mode: str,
) -> list[str]:
    if generation_mode == "official_closed_day":
        return [
            "cierre_canonico",
            "base_nocturna_canonica",
        ]

    if generation_mode == "manual_preview":
        if track_date == _get_track_local_today():
            return ["preview_operativo"]

        return [
            "cierre_canonico",
            "base_nocturna_canonica",
        ]

    raise ValueError(f"generation_mode inválido: {generation_mode!r}")


def _resolve_track_daily_history_version_for_query(
    *,
    track_date: date,
    generation_mode: str,
):
    for version_type in _resolve_track_daily_history_version_type_candidates(
        track_date=track_date,
        generation_mode=generation_mode,
    ):
        version = get_current_track_daily_version(
            track_date=track_date,
            version_type=version_type,
        )

        if version is not None and version.status == "success":
            return version

    return None


def _resolve_track_branch_history_rows(
    *,
    sucursal_canon: str,
    generation_mode: str,
    candidate_dates: list[date],
) -> list[TrackDailyMartORM]:
    resolved_rows: list[TrackDailyMartORM] = []

    for candidate_date in candidate_dates:
        resolved_version = _resolve_track_daily_history_version_for_query(
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
        run_track_agregadoras_integration_endpoint()

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

        resolved_version = _resolve_current_track_daily_version_for_query(
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

        resolved_version = _resolve_current_track_daily_version_for_query(
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
        