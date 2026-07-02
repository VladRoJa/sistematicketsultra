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


def _confidence_from_months(months_count: int) -> str:
    if months_count >= 24:
        return "alta"

    if months_count >= 12:
        return "media"

    if months_count >= 1:
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
        "target_month_number": target_month.month,
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
        "history_start_date": history_start_date,
        "history_end_date": history_end_date,
    }

    branch_join_filter = ""

    if scope == "branch":
        if not branch:
            raise ValueError("branch es requerido cuando scope=branch.")

        params["branch"] = branch.strip().upper()
        branch_join_filter = "AND upper(trim(a.sucursal_canon)) = :branch"

    rows = db.session.execute(
        text(
            f"""
            WITH canonical AS (
                SELECT
                    s.id AS snapshot_id,
                    s.business_date,
                    date_trunc('month', s.business_date)::date AS snapshot_month
                FROM venta_total_snapshots s
                WHERE s.report_type_key = 'venta_total'
                  AND s.snapshot_kind = 'daily'
                  AND s.is_canonical = true
                  AND s.business_date >= :history_start_date
                  AND s.business_date < :history_end_date
                  AND EXTRACT(MONTH FROM s.business_date)::int = :target_month_number
            ),
            clean AS (
                SELECT
                    c.snapshot_month,
                    a.sucursal_canon,
                    to_date(r.fecha, 'DD-MM-YY') AS fecha_venta,
                    EXTRACT(DAY FROM to_date(r.fecha, 'DD-MM-YY'))::int AS day_of_month,
                    r.total
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
                  {branch_join_filter}
            ),
            daily AS (
                SELECT
                    snapshot_month,
                    day_of_month,
                    SUM(total) AS daily_total
                FROM clean
                GROUP BY snapshot_month, day_of_month
            )
            SELECT
                COUNT(DISTINCT snapshot_month) AS historical_months,
                COALESCE(SUM(daily_total), 0) AS historical_month_total,
                COALESCE(SUM(daily_total) FILTER (WHERE day_of_month <= :cutoff_day), 0) AS historical_mtd_total,
                COUNT(DISTINCT day_of_month) AS distinct_days
            FROM daily
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        {
            **params,
            "cutoff_day": cutoff_day,
        },
    ).mappings().first()

    if not rows:
        historical_months = 0
        historical_month_total = 0.0
        historical_mtd_total = 0.0
        distinct_days = 0
    else:
        historical_months = int(rows["historical_months"] or 0)
        historical_month_total = _to_float(rows["historical_month_total"]) or 0.0
        historical_mtd_total = _to_float(rows["historical_mtd_total"]) or 0.0
        distinct_days = int(rows["distinct_days"] or 0)

    progress_pct = None

    if historical_month_total > 0:
        progress_pct = historical_mtd_total / historical_month_total

    return {
        "source": "branch" if scope == "branch" else "national",
        "historical_months": historical_months,
        "historical_month_total": historical_month_total,
        "historical_mtd_total": historical_mtd_total,
        "historical_remaining_total": max(historical_month_total - historical_mtd_total, 0.0),
        "historical_progress_pct": progress_pct,
        "distinct_days": distinct_days,
        "confidence": _confidence_from_months(historical_months),
    }


def _build_history_coverage(*, target_month: date, branch: str | None) -> dict[str, Any]:
    history_start_date, history_end_date = _build_history_window(target_month)

    params: dict[str, Any] = {
        "excluded_branches": tuple(EXCLUDED_BRANCHES),
        "history_start_date": history_start_date,
        "history_end_date": history_end_date,
    }

    branch_filter = ""

    if branch:
        params["branch"] = branch.strip().upper()
        branch_filter = "AND upper(trim(a.sucursal_canon)) = :branch"

    rows = db.session.execute(
        text(
            f"""
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
                  {branch_filter}
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
        "confidence": _confidence_from_months(months_count),
    }


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

    coverage = _build_history_coverage(
        target_month=target_month,
        branch=branch if scope == "branch" else None,
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
        "data_quality": {
            "goal_status": goal_status,
            "goal_status_message": (
                "Meta mensual no cargada. El ritmo contra meta se activará automáticamente cuando exista meta_faycgo_mes."
                if goal_status == "pending"
                else (
                    "Meta mensual parcialmente cargada. El ritmo contra meta se mantiene desactivado hasta tener metas completas."
                    if goal_status == "partial"
                    else None
                )
            ),
            "history_coverage": coverage,
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
            "confidence": coverage["confidence"] if scope == "branch" else curve["confidence"],
        },
        "historical_curve": curve,
    }
