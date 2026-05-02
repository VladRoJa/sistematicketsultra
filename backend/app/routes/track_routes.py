#   backend\app\routes\track_routes.py


from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from app.extensions import db

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app.models.warehouse import TrackDailyMartORM
from app.warehouse.services.track_daily_pipeline_service import (
    run_track_agregadoras_integration_for_date,
    run_track_daily_pipeline_for_date,
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


def _require_admin_role() -> None:
    claims = get_jwt()
    role = str(claims.get("rol") or "").strip().upper()

    if role not in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}:
        raise PermissionError("No autorizado para ejecutar o consultar el Track.")


def _serialize_decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _serialize_track_daily_mart_row(row: TrackDailyMartORM) -> dict[str, Any]:
    return {
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
        "source_snapshot_id_desempeno": row.source_snapshot_id_desempeno,
        "source_snapshot_id_ingresos": row.source_snapshot_id_ingresos,
        "source_snapshot_id_nuevos": row.source_snapshot_id_nuevos,
        "source_snapshot_id_domiciliados": row.source_snapshot_id_domiciliados,
    }


@track_bp.route("/run-daily-pipeline", methods=["POST"])
@jwt_required()
def run_track_daily_pipeline_endpoint():
    try:
        _require_admin_role()

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
        _require_admin_role()

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
        _require_admin_role()

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

        rows = (
            TrackDailyMartORM.query.filter_by(
                track_date=track_date,
                generation_mode=generation_mode,
            )
            .order_by(TrackDailyMartORM.sucursal_canon.asc())
            .all()
        )

        return jsonify(
            {
                "status": "ok",
                "track_date": track_date.isoformat(),
                "generation_mode": generation_mode,
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
        
        
@track_bp.route("/branch-history", methods=["GET"])
@jwt_required()
def get_track_branch_history_endpoint():
    try:
        _require_admin_role()

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

            rows = (
                TrackDailyMartORM.query.filter_by(
                    sucursal_canon=sucursal_canon,
                    generation_mode=generation_mode,
                )
                .filter(db.extract("year", TrackDailyMartORM.track_date) == target_year)
                .filter(db.extract("month", TrackDailyMartORM.track_date) == target_month)
                .order_by(TrackDailyMartORM.track_date.asc())
                .all()
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

        rows = (
            TrackDailyMartORM.query.filter_by(
                sucursal_canon=sucursal_canon,
                generation_mode=generation_mode,
            )
            .order_by(TrackDailyMartORM.track_date.desc())
            .limit(days)
            .all()
        )

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

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "Falló la consulta del historial del Track por sucursal.",
                "detail": str(exc),
            }
        ), 500