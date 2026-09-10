from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, TypedDict

from sqlalchemy import text

from app.extensions import db


BAJAS_FORECAST_METHOD = "chain_daily_median_share_of_month_close"


class BajasHistoricalProgressPoint(TypedDict):
    day: int
    samples_count: int
    p25: Decimal
    median: Decimal
    p75: Decimal


class BajasHistoricalProgressCurve(TypedDict):
    status: Literal["available", "no_history"]
    method: Literal["chain_daily_median_share_of_month_close"]
    target_month: date
    history_end_exclusive: date
    points: dict[int, BajasHistoricalProgressPoint]


def build_bajas_historical_progress_curve(
    *,
    target_month: date,
) -> BajasHistoricalProgressCurve:
    """Build the historical monthly-progress curve used to forecast bajas.

    The model measures, for every day of the month, what share of the final
    monthly bajas had normally been reported by that day. It uses canonical
    daily KPI Desempeno snapshots from complete months before ``target_month``
    and the chain-level median as the expected progress factor.

    Percentiles are returned as fractions (for example, ``Decimal("0.338")``
    means 33.8%). P25/P75 are kept for audit/sensitivity; the operational
    forecast uses the median.
    """

    normalized_target_month = target_month.replace(day=1)

    query = text(
        """
        WITH canonical_snapshots AS (
            SELECT DISTINCT ON (business_date)
                id,
                business_date,
                DATE_TRUNC('month', business_date)::date AS mes
            FROM kpi_desempeno_snapshots
            WHERE report_type_key = 'kpi_desempeno'
              AND snapshot_kind = 'daily'
              AND is_canonical = TRUE
              AND business_date < :target_month
            ORDER BY business_date, id DESC
        ),
        daily_chain AS (
            SELECT
                s.mes,
                s.business_date,
                EXTRACT(DAY FROM s.business_date)::int AS dia_mes,
                SUM(r.bajas)::numeric AS bajas_cadena
            FROM canonical_snapshots s
            JOIN kpi_desempeno_snapshot_rows r
              ON r.snapshot_id = s.id
            WHERE UPPER(TRIM(r.sucursal)) <> 'BECA'
            GROUP BY
                s.mes,
                s.business_date
        ),
        month_close_raw AS (
            SELECT DISTINCT ON (mes)
                mes,
                business_date AS fecha_cierre,
                bajas_cadena AS bajas_cierre
            FROM daily_chain
            ORDER BY mes, business_date DESC
        ),
        month_close AS (
            SELECT *
            FROM month_close_raw
            WHERE fecha_cierre >= (
                mes + INTERVAL '1 month' - INTERVAL '2 days'
            )::date
        ),
        paired AS (
            SELECT
                d.dia_mes,
                d.bajas_cadena / NULLIF(c.bajas_cierre, 0) AS pct_del_cierre
            FROM daily_chain d
            JOIN month_close c
              ON c.mes = d.mes
            WHERE c.bajas_cierre > 0
        )
        SELECT
            dia_mes,
            COUNT(*) AS meses_disponibles,
            PERCENTILE_CONT(0.25)
                WITHIN GROUP (ORDER BY pct_del_cierre)::numeric AS pct_cierre_p25,
            PERCENTILE_CONT(0.50)
                WITHIN GROUP (ORDER BY pct_del_cierre)::numeric AS pct_cierre_mediana,
            PERCENTILE_CONT(0.75)
                WITHIN GROUP (ORDER BY pct_del_cierre)::numeric AS pct_cierre_p75
        FROM paired
        GROUP BY dia_mes
        ORDER BY dia_mes
        """
    )

    result_rows = db.session.execute(
        query,
        {"target_month": normalized_target_month},
    ).mappings().all()

    points: dict[int, BajasHistoricalProgressPoint] = {}

    for row in result_rows:
        day = int(row["dia_mes"])
        p25 = _to_decimal(row["pct_cierre_p25"])
        median = _to_decimal(row["pct_cierre_mediana"])
        p75 = _to_decimal(row["pct_cierre_p75"])

        if p25 is None or median is None or p75 is None or median <= 0:
            continue

        points[day] = {
            "day": day,
            "samples_count": int(row["meses_disponibles"]),
            "p25": p25,
            "median": median,
            "p75": p75,
        }

    return {
        "status": "available" if points else "no_history",
        "method": BAJAS_FORECAST_METHOD,
        "target_month": normalized_target_month,
        "history_end_exclusive": normalized_target_month,
        "points": points,
    }


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
