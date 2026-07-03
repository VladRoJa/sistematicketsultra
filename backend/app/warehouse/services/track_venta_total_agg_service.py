from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import bindparam, text

from app.extensions import db


EXCLUDED_BRANCHES = {"CORPORATIVO", "GIMNASIO PRUEBA", "LA_VIGA"}


def aggregate_venta_total_snapshot(snapshot_id: int, *, commit: bool = True) -> dict[str, Any]:
    """
    Rebuilds the daily branch aggregation for one canonical venta_total snapshot.
    """
    snapshot = db.session.execute(
        text(
            """
            SELECT
                id,
                business_date,
                date_trunc('month', business_date)::date AS business_month
            FROM venta_total_snapshots
            WHERE id = :snapshot_id
              AND report_type_key = 'venta_total'
              AND snapshot_kind = 'daily'
              AND is_canonical = true
            """
        ),
        {"snapshot_id": snapshot_id},
    ).mappings().first()

    if not snapshot:
        return {
            "status": "skipped",
            "snapshot_id": snapshot_id,
            "reason": "snapshot_not_found_or_not_canonical_venta_total_daily",
            "rows_deleted": 0,
            "rows_inserted": 0,
        }

    deleted = db.session.execute(
        text(
            """
            DELETE FROM track_venta_total_daily_branch_agg
            WHERE snapshot_id = :snapshot_id
            """
        ),
        {"snapshot_id": snapshot_id},
    ).rowcount or 0

    insert_result = db.session.execute(
        text(
            """
            INSERT INTO track_venta_total_daily_branch_agg (
                snapshot_id,
                business_month,
                sale_date,
                day_of_month,
                sucursal_canon,
                total,
                row_count,
                created_at,
                updated_at
            )
            SELECT
                s.id AS snapshot_id,
                date_trunc('month', s.business_date)::date AS business_month,
                to_date(r.fecha, 'DD-MM-YY')::date AS sale_date,
                EXTRACT(DAY FROM to_date(r.fecha, 'DD-MM-YY'))::int AS day_of_month,
                upper(trim(a.sucursal_canon)) AS sucursal_canon,
                round(sum(r.total)::numeric, 2) AS total,
                count(*)::int AS row_count,
                now() AS created_at,
                now() AS updated_at
            FROM venta_total_snapshots s
            JOIN venta_total_snapshot_rows r
              ON r.snapshot_id = s.id
            JOIN track_branch_aliases a
              ON a.source_family = 'gasca_family'
             AND a.is_active = true
             AND upper(trim(a.raw_branch_name)) = upper(trim(r.sucursal))
            WHERE s.id = :snapshot_id
              AND s.report_type_key = 'venta_total'
              AND s.snapshot_kind = 'daily'
              AND s.is_canonical = true
              AND r.fecha ~ '^[0-9]{2}-[0-9]{2}-[0-9]{2}$'
              AND to_date(r.fecha, 'DD-MM-YY') >= date_trunc('month', s.business_date)::date
              AND to_date(r.fecha, 'DD-MM-YY') < (date_trunc('month', s.business_date)::date + interval '1 month')
              AND upper(trim(r.estatus)) = 'ACTIVO'
              AND r.total > 0
              AND upper(trim(r.sucursal)) NOT IN :excluded_branches
              AND upper(trim(a.sucursal_canon)) NOT IN :excluded_branches
            GROUP BY
                s.id,
                date_trunc('month', s.business_date)::date,
                to_date(r.fecha, 'DD-MM-YY')::date,
                EXTRACT(DAY FROM to_date(r.fecha, 'DD-MM-YY'))::int,
                upper(trim(a.sucursal_canon))
            """
        ).bindparams(bindparam("excluded_branches", expanding=True)),
        {
            "snapshot_id": snapshot_id,
            "excluded_branches": tuple(EXCLUDED_BRANCHES),
        },
    )

    inserted = insert_result.rowcount or 0

    if commit:
        db.session.commit()

    return {
        "status": "ok",
        "snapshot_id": snapshot_id,
        "business_month": snapshot["business_month"].isoformat(),
        "business_date": snapshot["business_date"].isoformat(),
        "rows_deleted": deleted,
        "rows_inserted": inserted,
    }


def backfill_venta_total_daily_branch_agg(
    *,
    start_month: date | None = None,
    end_month_exclusive: date | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Backfills aggregation for canonical venta_total daily snapshots.

    start_month and end_month_exclusive compare against date_trunc('month', business_date).
    Commits per snapshot to avoid one huge transaction.
    """
    params: dict[str, Any] = {}

    filters = [
        "report_type_key = 'venta_total'",
        "snapshot_kind = 'daily'",
        "is_canonical = true",
    ]

    if start_month:
        filters.append("date_trunc('month', business_date)::date >= :start_month")
        params["start_month"] = start_month

    if end_month_exclusive:
        filters.append("date_trunc('month', business_date)::date < :end_month_exclusive")
        params["end_month_exclusive"] = end_month_exclusive

    limit_sql = ""

    if limit is not None:
        limit_sql = "LIMIT :limit"
        params["limit"] = int(limit)

    snapshots = db.session.execute(
        text(
            f"""
            SELECT
                id,
                business_date,
                date_trunc('month', business_date)::date AS business_month
            FROM venta_total_snapshots
            WHERE {' AND '.join(filters)}
            ORDER BY business_date, id
            {limit_sql}
            """
        ),
        params,
    ).mappings().all()

    results: list[dict[str, Any]] = []
    total_inserted = 0
    total_deleted = 0

    for snapshot in snapshots:
        result = aggregate_venta_total_snapshot(int(snapshot["id"]), commit=True)
        results.append(result)
        total_inserted += int(result.get("rows_inserted") or 0)
        total_deleted += int(result.get("rows_deleted") or 0)

    return {
        "status": "ok",
        "snapshots_processed": len(results),
        "rows_deleted": total_deleted,
        "rows_inserted": total_inserted,
        "results": results,
    }



def aggregate_missing_venta_total_snapshots(
    *,
    start_month: date | None = None,
    end_month_exclusive: date | None = None,
    max_business_date: date | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Aggregates canonical venta_total daily snapshots that do not have derived rows yet.

    max_business_date is useful for official forecast flows where the current
    in-progress day should not be included until it becomes a closed day.
    """
    params: dict[str, Any] = {}

    filters = [
        "s.report_type_key = 'venta_total'",
        "s.snapshot_kind = 'daily'",
        "s.is_canonical = true",
        "a.snapshot_id IS NULL",
    ]

    if start_month:
        filters.append("date_trunc('month', s.business_date)::date >= :start_month")
        params["start_month"] = start_month

    if end_month_exclusive:
        filters.append("date_trunc('month', s.business_date)::date < :end_month_exclusive")
        params["end_month_exclusive"] = end_month_exclusive

    if max_business_date:
        filters.append("s.business_date <= :max_business_date")
        params["max_business_date"] = max_business_date

    limit_sql = ""

    if limit is not None:
        limit_sql = "LIMIT :limit"
        params["limit"] = int(limit)

    snapshots = db.session.execute(
        text(
            f"""
            SELECT
                s.id,
                s.business_date,
                date_trunc('month', s.business_date)::date AS business_month
            FROM venta_total_snapshots s
            LEFT JOIN (
                SELECT DISTINCT snapshot_id
                FROM track_venta_total_daily_branch_agg
            ) a
              ON a.snapshot_id = s.id
            WHERE {' AND '.join(filters)}
            ORDER BY s.business_date, s.id
            {limit_sql}
            """
        ),
        params,
    ).mappings().all()

    results: list[dict[str, Any]] = []
    total_inserted = 0
    total_deleted = 0

    for snapshot in snapshots:
        result = aggregate_venta_total_snapshot(int(snapshot["id"]), commit=True)
        results.append(result)
        total_inserted += int(result.get("rows_inserted") or 0)
        total_deleted += int(result.get("rows_deleted") or 0)

    return {
        "status": "ok",
        "snapshots_processed": len(results),
        "rows_deleted": total_deleted,
        "rows_inserted": total_inserted,
        "max_business_date": max_business_date.isoformat() if max_business_date else None,
        "results": results,
    }

def get_venta_total_daily_branch_agg_health() -> dict[str, Any]:
    row = db.session.execute(
        text(
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT snapshot_id) AS snapshots,
                COUNT(DISTINCT business_month) AS months,
                MIN(business_month) AS first_month,
                MAX(business_month) AS last_month,
                MIN(sale_date) AS first_sale_date,
                MAX(sale_date) AS last_sale_date,
                COUNT(DISTINCT sucursal_canon) AS branches
            FROM track_venta_total_daily_branch_agg
            """
        )
    ).mappings().first()

    return {
        "total_rows": int(row["total_rows"] or 0),
        "snapshots": int(row["snapshots"] or 0),
        "months": int(row["months"] or 0),
        "first_month": row["first_month"].isoformat() if row and row["first_month"] else None,
        "last_month": row["last_month"].isoformat() if row and row["last_month"] else None,
        "first_sale_date": row["first_sale_date"].isoformat() if row and row["first_sale_date"] else None,
        "last_sale_date": row["last_sale_date"].isoformat() if row and row["last_sale_date"] else None,
        "branches": int(row["branches"] or 0),
    }
