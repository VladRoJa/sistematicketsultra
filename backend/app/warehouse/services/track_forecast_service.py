from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, text

from app.extensions import db


EXCLUDED_BRANCHES = {
    "CORPORATIVO",
    "GIMNASIO PRUEBA",
    "LA_VIGA",
}


def _to_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


def _first_day_of_month(value: date) -> date:
    return date(value.year, value.month, 1)


def _build_history_window(target_month: date) -> tuple[date, date]:
    return date(target_month.year - 3, 1, 1), date(target_month.year, 1, 1)


def _confidence_from_coverage_months(months_count: int) -> str:
    if months_count >= 24:
        return "alta"

    if months_count >= 12:
        return "media"

    if months_count >= 1:
        return "baja"

    return "sin_historia"


def _confidence_from_comparable_months(months_count: int) -> str:
    if months_count >= 3:
        return "alta"

    if months_count == 2:
        return "media"

    if months_count == 1:
        return "baja"

    return "sin_historia"


def _goal_status_from_count(*, expected_count: int, available_count: int) -> str:
    if expected_count <= 0:
        return "pending"

    if available_count == expected_count:
        return "available"

    if available_count > 0:
        return "partial"

    return "pending"


def _status_vs_goal(*, gap_pct: float | None, progress_pct: float) -> str | None:
    if gap_pct is None:
        return None

    if progress_pct < 0.15:
        return "inicio_mes_baja_confianza"

    if gap_pct <= -0.08:
        return "rojo"

    if gap_pct <= -0.03:
        return "amarillo"

    if gap_pct >= 0.05:
        return "destacado"

    return "en_ritmo"


def _get_selected_mart_rows(
    *,
    track_daily_version_id: int,
    scope: str,
    branch: str | None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "track_daily_version_id": track_daily_version_id,
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
    }

    branch_filter = ""

    if scope == "branch":
        if not branch:
            raise ValueError("branch es requerido cuando scope=branch.")

        params["branch"] = branch.strip().upper()
        branch_filter = "AND upper(trim(sucursal_canon)) = :branch"

    rows = db.session.execute(
        text(
            f"""
            SELECT
                sucursal_canon,
                target_month,
                COALESCE(ingreso_real_total_mtd, ingreso_real_mtd, 0) AS real_mtd,
                ingreso_real_base_mtd,
                ingreso_real_agregadora_mtd,
                meta_faycgo_mes
            FROM track_daily_mart
            WHERE track_daily_version_id = :track_daily_version_id
              AND upper(trim(sucursal_canon)) NOT IN :excluded_branches
              {branch_filter}
            ORDER BY sucursal_canon
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]


def _resolve_goal_from_track_monthly_targets(
    *,
    target_month: date,
    selected_branches: list[str],
) -> tuple[float | None, int]:
    if not selected_branches:
        return None, 0

    rows = db.session.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE meta_faycgo_mes IS NOT NULL) AS available_count,
                SUM(meta_faycgo_mes) AS goal_month
            FROM track_monthly_targets
            WHERE target_month = :target_month
              AND is_active = true
              AND sucursal_canon IN :selected_branches
            """
        ).bindparams(bindparam("selected_branches", expanding=True)),
        {
            "target_month": target_month,
            "selected_branches": tuple(selected_branches),
        },
    ).mappings().first()

    if not rows:
        return None, 0

    return _to_float(rows["goal_month"]), int(rows["available_count"] or 0)


def _build_historical_curve(
    *,
    target_month: date,
    cutoff_day: int,
    scope: str,
    branch: str | None,
) -> dict[str, Any]:
    history_start_date, history_end_date = _build_history_window(target_month)

    params: dict[str, Any] = {
        "history_start_date": history_start_date,
        "history_end_date": history_end_date,
        "target_month_number": target_month.month,
        "cutoff_day": cutoff_day,
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
    }

    branch_filter = ""

    if scope == "branch" and branch:
        branch_filter = "AND upper(trim(a.sucursal_canon)) = :branch"
        params["branch"] = branch.strip().upper()

    row = db.session.execute(
        text(
            f"""
            WITH historical AS (
                SELECT
                    a.business_month,
                    a.sale_date,
                    a.day_of_month,
                    upper(trim(a.sucursal_canon)) AS sucursal_canon,
                    a.total
                FROM track_venta_total_daily_branch_agg a
                JOIN venta_total_snapshots s
                  ON s.id = a.snapshot_id
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND a.business_month >= :history_start_date
                  AND a.business_month < :history_end_date
                  AND EXTRACT(MONTH FROM a.business_month)::int = :target_month_number
                  AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
                  {branch_filter}
            )
            SELECT
                COUNT(DISTINCT business_month) AS historical_months,
                COALESCE(SUM(total), 0)::numeric AS historical_month_total,
                COALESCE(SUM(CASE WHEN day_of_month <= :cutoff_day THEN total ELSE 0 END), 0)::numeric AS historical_mtd_total,
                COALESCE(SUM(CASE WHEN day_of_month > :cutoff_day THEN total ELSE 0 END), 0)::numeric AS historical_remaining_total,
                COUNT(DISTINCT day_of_month)::int AS distinct_days
            FROM historical
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        params,
    ).mappings().first()

    historical_months = int(row["historical_months"] or 0) if row else 0
    historical_month_total = float(row["historical_month_total"] or 0) if row else 0.0
    historical_mtd_total = float(row["historical_mtd_total"] or 0) if row else 0.0
    historical_remaining_total = float(row["historical_remaining_total"] or 0) if row else 0.0
    distinct_days = int(row["distinct_days"] or 0) if row else 0

    historical_progress_pct = None

    if historical_month_total > 0:
        historical_progress_pct = historical_mtd_total / historical_month_total

    return {
        "source": "branch" if scope == "branch" else "national",
        "historical_months": historical_months,
        "historical_month_total": historical_month_total,
        "historical_mtd_total": historical_mtd_total,
        "historical_remaining_total": historical_remaining_total,
        "historical_progress_pct": historical_progress_pct,
        "distinct_days": distinct_days,
        "confidence": _confidence_from_comparable_months(historical_months),
    }



def _build_history_coverage(*, target_month: date, branch: str | None) -> dict[str, Any]:
    history_start_date, history_end_date = _build_history_window(target_month)

    if not branch:
        rows = db.session.execute(
            text(
                """
                SELECT
                    COUNT(DISTINCT date_trunc('month', business_date)::date) AS months_count,
                    MIN(date_trunc('month', business_date)::date) AS first_month,
                    MAX(date_trunc('month', business_date)::date) AS last_month
                FROM venta_total_snapshots
                WHERE report_type_key = 'venta_total'
                  AND snapshot_kind = 'daily'
                  AND is_canonical = true
                  AND business_date >= :history_start_date
                  AND business_date < :history_end_date
                """
            ),
            {
                "history_start_date": history_start_date,
                "history_end_date": history_end_date,
            },
        ).mappings().first()

        months_count = int(rows["months_count"] or 0) if rows else 0

        return {
            "months_count": months_count,
            "first_month": rows["first_month"].isoformat() if rows and rows["first_month"] else None,
            "last_month": rows["last_month"].isoformat() if rows and rows["last_month"] else None,
            "confidence": _confidence_from_coverage_months(months_count),
        }

    params: dict[str, Any] = {
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
        "history_start_date": history_start_date,
        "history_end_date": history_end_date,
        "branch": branch.strip().upper(),
    }

    rows = db.session.execute(
        text(
            """
            WITH canonical AS (
                SELECT
                    s.id AS snapshot_id,
                    date_trunc('month', s.business_date)::date AS snapshot_month
                FROM venta_total_snapshots s
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND s.business_date >= :history_start_date
                  AND s.business_date < :history_end_date
            ),
            clean AS (
                SELECT DISTINCT
                    c.snapshot_month,
                    a.sucursal_canon
                FROM canonical c
                JOIN venta_total_snapshot_rows r
                  ON r.snapshot_id = c.snapshot_id
                JOIN track_branch_aliases a
                  ON a.source_family = 'gasca_family'
                 AND a.is_active = true
                 AND upper(trim(a.raw_branch_name)) = upper(trim(r.sucursal))
                WHERE upper(trim(r.estatus)) = 'ACTIVO'
                  AND r.total > 0
                  AND to_date(r.fecha, 'DD-MM-YY') >= c.snapshot_month
                  AND to_date(r.fecha, 'DD-MM-YY') < (c.snapshot_month + interval '1 month')
                  AND upper(trim(r.sucursal)) NOT IN :excluded_branches
                  AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
                  AND upper(trim(a.sucursal_canon)) = :branch
            )
            SELECT
                COUNT(DISTINCT snapshot_month) AS months_count,
                MIN(snapshot_month) AS first_month,
                MAX(snapshot_month) AS last_month
            FROM clean
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        params,
    ).mappings().first()

    months_count = int(rows["months_count"] or 0) if rows else 0

    return {
        "months_count": months_count,
        "first_month": rows["first_month"].isoformat() if rows and rows["first_month"] else None,
        "last_month": rows["last_month"].isoformat() if rows and rows["last_month"] else None,
        "confidence": _confidence_from_coverage_months(months_count),
    }




def _format_currency_mxn(value: float | None) -> str:
    if value is None:
        return "sin dato"

    return f"${value:,.0f} MXN"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "sin dato"

    return f"{value * 100:.1f}%"


def _goal_status_message(goal_status: str) -> str | None:
    if goal_status == "pending":
        return "Meta mensual no cargada. El ritmo contra meta se activará automáticamente cuando exista meta_faycgo_mes."

    if goal_status == "partial":
        return "Meta mensual parcialmente cargada. El ritmo contra meta se mantiene desactivado hasta tener metas completas."

    return None


def _resolve_aggregated_canonical_cutoff(
    *,
    target_month: date,
    track_date: date,
    scope: str,
    branch: str | None,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {
        "target_month": target_month,
        "track_date": track_date,
    }

    branch_filter = ""

    if scope == "branch" and branch:
        branch_filter = "AND upper(trim(a.sucursal_canon)) = :branch"
        params["branch"] = branch.strip().upper()

    row = db.session.execute(
        text(
            f"""
            SELECT
                s.id AS snapshot_id,
                s.business_date,
                COUNT(*)::int AS aggregate_rows,
                MIN(a.sale_date)::date AS first_sale_date,
                MAX(a.sale_date)::date AS last_sale_date,
                COUNT(DISTINCT a.sucursal_canon)::int AS branches
            FROM track_venta_total_daily_branch_agg a
            JOIN venta_total_snapshots s
              ON s.id = a.snapshot_id
            WHERE s.report_type_key = 'venta_total'
              AND s.snapshot_kind = 'daily'
              AND s.is_canonical = true
              AND a.business_month = :target_month
              AND s.business_date <= :track_date
              {branch_filter}
            GROUP BY
                s.id,
                s.business_date
            ORDER BY
                s.business_date DESC,
                s.id DESC
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()

    if not row:
        return None

    return {
        "snapshot_id": int(row["snapshot_id"]),
        "business_date": row["business_date"].isoformat() if row["business_date"] else None,
        "aggregate_rows": int(row["aggregate_rows"] or 0),
        "first_sale_date": row["first_sale_date"].isoformat() if row["first_sale_date"] else None,
        "last_sale_date": row["last_sale_date"].isoformat() if row["last_sale_date"] else None,
        "branches": int(row["branches"] or 0),
    }


def _build_forecast_cutoff(
    *,
    track_date: date,
    target_month: date,
    cutoff_day: int,
    generation_mode: str,
    canonical_cutoff: dict[str, Any] | None,
) -> dict[str, Any]:
    is_official = generation_mode == "official_closed_day"

    return {
        "track_date": track_date.isoformat(),
        "target_month": target_month.isoformat(),
        "cutoff_day": cutoff_day,
        "generation_mode": generation_mode,
        "is_official_forecast": is_official,
        "basis": "official_closed_day" if is_official else "preview_operativo",
        "canonical_cutoff": canonical_cutoff,
        "message": (
            "Proyección basada en día cerrado oficial."
            if is_official
            else "Proyección basada en preview operativo; debe leerse como pulso preliminar, no como cierre oficial."
        ),
    }


def _build_executive_status(
    *,
    projected_close: float | None,
    trend_factor: float | None,
    goal_status: str,
    gap_vs_weighted_goal_pct: float | None,
    branch_projection_quality_issue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if branch_projection_quality_issue:
        return {
            "level": "warning",
            "code": "insufficient_branch_history",
            "title": "Histórico insuficiente para proyectar sucursal",
            "message": branch_projection_quality_issue["message"],
            "primary_metric_label": "Proyección de cierre",
            "primary_metric_value": None,
            "primary_metric_unit": "MXN",
        }

    if projected_close is None:
        return {
            "level": "neutral",
            "code": "no_projection",
            "title": "Sin proyección disponible",
            "message": "No hay histórico suficiente para calcular una proyección confiable.",
            "primary_metric_label": "Proyección de cierre",
            "primary_metric_value": None,
            "primary_metric_unit": "MXN",
        }

    if goal_status == "available" and gap_vs_weighted_goal_pct is not None:
        if gap_vs_weighted_goal_pct <= -0.05:
            level = "danger"
            code = "below_weighted_goal"
            title = "Por debajo de la meta ponderada"
        elif gap_vs_weighted_goal_pct < -0.02:
            level = "warning"
            code = "slightly_below_weighted_goal"
            title = "Ligeramente por debajo de la meta ponderada"
        elif gap_vs_weighted_goal_pct > 0.02:
            level = "success"
            code = "above_weighted_goal"
            title = "Por encima de la meta ponderada"
        else:
            level = "neutral"
            code = "near_weighted_goal"
            title = "Cerca de la meta ponderada"

        return {
            "level": level,
            "code": code,
            "title": title,
            "message": f"La proyección actual de cierre es {_format_currency_mxn(projected_close)}.",
            "primary_metric_label": "Proyección de cierre",
            "primary_metric_value": projected_close,
            "primary_metric_unit": "MXN",
        }

    if trend_factor is None:
        return {
            "level": "neutral",
            "code": "projection_without_trend_factor",
            "title": "Proyección calculada sin factor de tendencia",
            "message": f"La proyección actual de cierre es {_format_currency_mxn(projected_close)}.",
            "primary_metric_label": "Proyección de cierre",
            "primary_metric_value": projected_close,
            "primary_metric_unit": "MXN",
        }

    if trend_factor < 0.85:
        level = "danger"
        code = "well_below_historical_pace"
        title = "Ritmo muy por debajo del histórico"
    elif trend_factor < 0.95:
        level = "warning"
        code = "below_historical_pace"
        title = "Ritmo por debajo del histórico"
    elif trend_factor <= 1.05:
        level = "neutral"
        code = "near_historical_pace"
        title = "Ritmo cercano al histórico"
    else:
        level = "success"
        code = "above_historical_pace"
        title = "Ritmo por encima del histórico"

    return {
        "level": level,
        "code": code,
        "title": title,
        "message": (
            f"El real MTD equivale al {_format_percent(trend_factor)} del avance histórico esperado. "
            f"La proyección actual de cierre es {_format_currency_mxn(projected_close)}."
        ),
        "primary_metric_label": "Proyección de cierre",
        "primary_metric_value": projected_close,
        "primary_metric_unit": "MXN",
    }


def _build_forecast_explanation(
    *,
    cutoff_day: int,
    real_mtd: float,
    projected_close: float | None,
    progress_pct: float | None,
    historical_mtd_total: float | None,
    trend_factor: float | None,
) -> dict[str, Any]:
    if projected_close is None or progress_pct is None:
        plain_text = "No hay histórico suficiente para explicar la proyección."
    else:
        plain_text = (
            f"Históricamente, al día {cutoff_day} se lleva {_format_percent(progress_pct)} del mes. "
            f"Con un real MTD de {_format_currency_mxn(real_mtd)}, "
            f"el cierre proyectado es {_format_currency_mxn(projected_close)}."
        )

    return {
        "formula_key": "real_mtd_divided_by_historical_progress_pct",
        "formula": "projected_close = real_mtd / historical_progress_pct",
        "plain_text": plain_text,
        "components": {
            "cutoff_day": cutoff_day,
            "real_mtd": real_mtd,
            "historical_progress_pct": progress_pct,
            "historical_expected_mtd": historical_mtd_total,
            "trend_factor": trend_factor,
            "projected_close": projected_close,
        },
    }



def _resolve_branch_projection_quality_issue(
    *,
    scope: str,
    curve: dict[str, Any],
    trend_factor: float | None,
) -> dict[str, Any] | None:
    if scope != "branch":
        return None

    historical_months = int(curve.get("historical_months") or 0)
    historical_mtd_total = float(curve.get("historical_mtd_total") or 0)
    confidence = str(curve.get("confidence") or "sin_historia")

    reasons: list[str] = []

    if historical_months < 3:
        reasons.append("La sucursal tiene menos de 3 meses comparables para este mes.")

    if confidence != "alta":
        reasons.append(f"La confianza histórica de la sucursal es {confidence}.")

    if historical_mtd_total < 50000:
        reasons.append("El histórico esperado MTD de la sucursal es demasiado bajo para proyectar con estabilidad.")

    if trend_factor is not None and trend_factor > 3:
        reasons.append("El factor de tendencia es extremo contra el histórico esperado de la sucursal.")

    if not reasons:
        return None

    return {
        "code": "insufficient_branch_history",
        "severity": "warning",
        "message": "Histórico insuficiente para proyectar esta sucursal con estabilidad.",
        "reasons": reasons,
        "thresholds": {
            "min_historical_months": 3,
            "min_historical_mtd_total": 50000,
            "max_trend_factor": 3,
        },
    }

def _build_forecast_warnings(
    *,
    generation_mode: str,
    goal_status: str,
    curve: dict[str, Any],
    canonical_cutoff: dict[str, Any] | None,
    branch_projection_quality_issue: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    if generation_mode != "official_closed_day":
        warnings.append({
            "code": "preview_operativo",
            "severity": "warning",
            "message": "La proyección usa preview operativo; si el día aún no está cerrado, puede variar o subestimar el cierre.",
        })

    if goal_status == "pending":
        warnings.append({
            "code": "goal_pending",
            "severity": "info",
            "message": "La meta mensual no está cargada. La brecha contra meta se activará cuando exista meta_faycgo_mes.",
        })
    elif goal_status == "partial":
        warnings.append({
            "code": "goal_partial",
            "severity": "warning",
            "message": "La meta mensual está parcialmente cargada. El ritmo contra meta se mantiene desactivado.",
        })

    if not canonical_cutoff:
        warnings.append({
            "code": "canonical_cutoff_missing",
            "severity": "warning",
            "message": "No se encontró corte canónico agregado para el mes y fecha solicitados.",
        })

    if int(curve.get("historical_months") or 0) < 3:
        warnings.append({
            "code": "low_comparable_history",
            "severity": "warning",
            "message": "La curva histórica tiene menos de 3 meses comparables.",
        })

    if branch_projection_quality_issue:
        warnings.append(branch_projection_quality_issue)

    return warnings

def build_venta_total_forecast(
    *,
    track_date: date,
    generation_mode: str,
    track_daily_version_id: int,
    scope: str = "national",
    branch: str | None = None,
) -> dict[str, Any]:
    scope = (scope or "national").strip().lower()

    if scope not in {"national", "branch"}:
        raise ValueError("scope inválido. Usa national o branch.")

    target_month = _first_day_of_month(track_date)
    cutoff_day = min(track_date.day, monthrange(track_date.year, track_date.month)[1])
    history_start_date, history_end_date = _build_history_window(target_month)

    mart_rows = _get_selected_mart_rows(
        track_daily_version_id=track_daily_version_id,
        scope=scope,
        branch=branch,
    )

    if scope == "branch" and not mart_rows:
        raise ValueError(f"No existe fila Track para branch={branch!r} en la versión resuelta.")

    selected_branches = [str(row["sucursal_canon"]) for row in mart_rows]

    real_mtd = sum((_to_float(row["real_mtd"]) or 0.0) for row in mart_rows)
    real_base_mtd = sum((_to_float(row["ingreso_real_base_mtd"]) or 0.0) for row in mart_rows)
    real_agregadora_mtd = sum((_to_float(row["ingreso_real_agregadora_mtd"]) or 0.0) for row in mart_rows)

    mart_goal_available_count = sum(1 for row in mart_rows if row.get("meta_faycgo_mes") is not None)
    mart_goal_total = sum((_to_float(row["meta_faycgo_mes"]) or 0.0) for row in mart_rows)

    expected_goal_count = len(mart_rows)
    goal_status = _goal_status_from_count(
        expected_count=expected_goal_count,
        available_count=mart_goal_available_count,
    )

    goal_month: float | None = None

    if goal_status == "available":
        goal_month = mart_goal_total
    else:
        fallback_goal, fallback_available_count = _resolve_goal_from_track_monthly_targets(
            target_month=target_month,
            selected_branches=selected_branches,
        )

        fallback_status = _goal_status_from_count(
            expected_count=expected_goal_count,
            available_count=fallback_available_count,
        )

        if fallback_status == "available":
            goal_status = "available"
            goal_month = fallback_goal
        elif fallback_status == "partial":
            goal_status = "partial"
            goal_month = None
        else:
            goal_status = "pending"
            goal_month = None

    curve = _build_historical_curve(
        target_month=target_month,
        cutoff_day=cutoff_day,
        scope=scope,
        branch=branch,
    )

    progress_pct = curve["historical_progress_pct"]

    projected_close = None
    trend_factor = None
    weighted_goal_mtd = None
    gap_vs_weighted_goal = None
    gap_vs_weighted_goal_pct = None
    status_vs_goal = None

    if progress_pct and progress_pct > 0:
        projected_close = real_mtd / progress_pct

        historical_mtd_total = curve["historical_mtd_total"]

        if historical_mtd_total > 0:
            trend_factor = real_mtd / historical_mtd_total

        if goal_status == "available" and goal_month is not None:
            weighted_goal_mtd = goal_month * progress_pct
            gap_vs_weighted_goal = real_mtd - weighted_goal_mtd

            if weighted_goal_mtd > 0:
                gap_vs_weighted_goal_pct = gap_vs_weighted_goal / weighted_goal_mtd

            status_vs_goal = _status_vs_goal(
                gap_pct=gap_vs_weighted_goal_pct,
                progress_pct=progress_pct,
            )

    branch_projection_quality_issue = _resolve_branch_projection_quality_issue(
        scope=scope,
        curve=curve,
        trend_factor=trend_factor,
    )

    if branch_projection_quality_issue:
        projected_close = None
        weighted_goal_mtd = None
        gap_vs_weighted_goal = None
        gap_vs_weighted_goal_pct = None
        status_vs_goal = None

    coverage = _build_history_coverage(
        target_month=target_month,
        branch=branch if scope == "branch" else None,
    )

    confidence = coverage["confidence"] if scope == "branch" else curve["confidence"]
    goal_status_message = _goal_status_message(goal_status)

    canonical_cutoff = _resolve_aggregated_canonical_cutoff(
        target_month=target_month,
        track_date=track_date,
        scope=scope,
        branch=branch,
    )

    forecast_cutoff = _build_forecast_cutoff(
        track_date=track_date,
        target_month=target_month,
        cutoff_day=cutoff_day,
        generation_mode=generation_mode,
        canonical_cutoff=canonical_cutoff,
    )

    executive_status = _build_executive_status(
        projected_close=projected_close,
        trend_factor=trend_factor,
        goal_status=goal_status,
        gap_vs_weighted_goal_pct=gap_vs_weighted_goal_pct,
        branch_projection_quality_issue=branch_projection_quality_issue,
    )

    forecast_explanation = _build_forecast_explanation(
        cutoff_day=cutoff_day,
        real_mtd=real_mtd,
        projected_close=projected_close,
        progress_pct=progress_pct,
        historical_mtd_total=curve["historical_mtd_total"],
        trend_factor=trend_factor,
    )

    warnings = _build_forecast_warnings(
        generation_mode=generation_mode,
        goal_status=goal_status,
        curve=curve,
        canonical_cutoff=canonical_cutoff,
        branch_projection_quality_issue=branch_projection_quality_issue,
    )

    return {
        "status": "ok",
        "metadata": {
            "track_date": track_date.isoformat(),
            "target_month": target_month.isoformat(),
            "generation_mode": generation_mode,
            "track_daily_version_id": track_daily_version_id,
            "scope": scope,
            "branch": branch.strip().upper() if branch else None,
            "selected_branches_count": len(selected_branches),
            "excluded_branches": sorted(EXCLUDED_BRANCHES),
            "history_window": {
                "start": history_start_date.isoformat(),
                "end_exclusive": history_end_date.isoformat(),
            },
        },
        "forecast_cutoff": forecast_cutoff,
        "executive_status": executive_status,
        "forecast_explanation": forecast_explanation,
        "warnings": warnings,
        "data_quality": {
            "goal_status": goal_status,
            "goal_status_message": goal_status_message,
            "history_coverage": coverage,
            "branch_projection_quality_issue": branch_projection_quality_issue,
        },
        "summary": {
            "real_mtd": real_mtd,
            "real_base_mtd": real_base_mtd,
            "real_agregadora_mtd": real_agregadora_mtd,
            "goal_month": goal_month,
            "historical_progress_pct": progress_pct,
            "historical_expected_mtd": curve["historical_mtd_total"],
            "historical_expected_remaining": curve["historical_remaining_total"],
            "trend_factor_raw": trend_factor,
            "projected_close": projected_close,
            "weighted_goal_mtd": weighted_goal_mtd,
            "gap_vs_weighted_goal": gap_vs_weighted_goal,
            "gap_vs_weighted_goal_pct": gap_vs_weighted_goal_pct,
            "status_vs_goal": status_vs_goal,
            "confidence": confidence,
        },
        "historical_curve": curve,
    }
