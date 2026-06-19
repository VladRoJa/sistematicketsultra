from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app.warehouse.services.kpi_desempeno_query_service import (
    KpiDesempenoQueryServiceError,
    build_historical_closing_section,
    build_monthly_closing_section,
    build_weekly_closing_section,
    build_weekly_branch_series_section,
)


track_kpi_desempeno_bp = Blueprint(
    "track_kpi_desempeno_bp",
    __name__,
)


def _get_current_role() -> str:
    claims = get_jwt()
    return str(claims.get("rol") or "").strip().upper()


def _require_kpi_desempeno_read_role() -> None:
    role = _get_current_role()

    if role not in {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
    }:
        raise PermissionError("No autorizado para consultar KPI Desempeño.")


def _get_default_target_month() -> str:
    today = datetime.now(ZoneInfo("America/Tijuana")).date()
    return f"{today.year:04d}-{today.month:02d}"


@track_kpi_desempeno_bp.route("/monthly-report", methods=["GET"])
@jwt_required()
def get_kpi_desempeno_monthly_report_endpoint():
    """
    Endpoint KPI Desempeño Fase 1.

    Fase 1:
    - cierre semanal de socios
    - cierre mensual de socios
    - histórico desde 2023 con granularidad controlada
    """
    try:
        _require_kpi_desempeno_read_role()

        target_month = (
            request.args.get("target_month")
            or _get_default_target_month()
        )
        start_month = request.args.get("start_month") or "2023-01"
        history_granularity = (
            request.args.get("history_granularity")
            or "quarterly"
        )

        weekly_branch_series_section = build_weekly_branch_series_section(
            start_month=start_month,
            end_month=target_month,
        )

        weekly_closing_section = build_weekly_closing_section(
            target_month=target_month,
        )

        monthly_closing_section = build_monthly_closing_section(
            target_month=target_month,
        )

        historical_closing_section = build_historical_closing_section(
            start_month=start_month,
            end_month=target_month,
            granularity=history_granularity,
        )

        response: dict[str, Any] = {
            "status": "ok",
            "module": "kpi_desempeno",
            "phase": "fase_1",
            "metadata": {
                "source": "warehouse",
                "report_type_key": "kpi_desempeno",
                "snapshot_kind": "daily",
                "canonical_only": True,
                "target_month": target_month,
                "start_month": start_month,
                "history_granularity": history_granularity,
                "timezone": "America/Tijuana",
                "permissions_mode": "beta_admin_only",
            },
                "sections": [
                weekly_branch_series_section,
                weekly_closing_section,
                monthly_closing_section,
                historical_closing_section,
            ],
        }

        return jsonify(response), 200

    except PermissionError as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 403

    except KpiDesempenoQueryServiceError as exc:
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
                "message": "Falló la consulta de KPI Desempeño.",
                "detail": str(exc),
            }
        ), 500




