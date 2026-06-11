#   backend\app\warehouse\services\warehouse_retention_service.py


from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app import db


WAREHOUSE_LOCAL_TZ = ZoneInfo("America/Tijuana")


def purge_venta_total_non_canonical_snapshots(
    *,
    retention_days: int = 7,
    batch_limit: int = 100,
    max_batches: int = 20,
    dry_run: bool = False,
) -> dict:
    """
    Purga snapshots estructurados no canónicos de venta_total.

    Reglas:
    - Conserva snapshots canónicos.
    - Conserva snapshots no canónicos recientes.
    - Purga snapshots no canónicos con business_date anterior al cutoff.
    - No toca warehouse_uploads ni archivos raw.
    - Las rows se eliminan por ON DELETE CASCADE desde venta_total_snapshots.
    """

    retention_days = max(int(retention_days or 7), 1)
    batch_limit = max(min(int(batch_limit or 100), 500), 1)
    max_batches = max(min(int(max_batches or 20), 100), 1)

    cutoff_date = datetime.now(WAREHOUSE_LOCAL_TZ).date() - timedelta(days=retention_days)

    if dry_run:
        row = db.session.execute(
            text(
                """
                SELECT
                  COUNT(DISTINCT s.id) AS target_snapshots,
                  COUNT(r.id) AS target_rows
                FROM public.venta_total_snapshots s
                LEFT JOIN public.venta_total_snapshot_rows r
                  ON r.snapshot_id = s.id
                WHERE COALESCE(s.is_canonical, false) = false
                  AND s.business_date < :cutoff_date
                """
            ),
            {"cutoff_date": cutoff_date},
        ).mappings().one()

        return {
            "report_type_key": "venta_total",
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "dry_run": True,
            "target_snapshots": int(row["target_snapshots"] or 0),
            "target_rows": int(row["target_rows"] or 0),
            "deleted_snapshots": 0,
            "deleted_rows": 0,
            "batches": 0,
        }

    total_deleted_snapshots = 0
    total_deleted_rows = 0
    batches = 0

    try:
        for _ in range(max_batches):
            row = db.session.execute(
                text(
                    """
                    WITH target AS (
                      SELECT id
                      FROM public.venta_total_snapshots
                      WHERE COALESCE(is_canonical, false) = false
                        AND business_date < :cutoff_date
                      ORDER BY business_date, id
                      LIMIT :batch_limit
                    ),
                    target_rows AS (
                      SELECT COUNT(*) AS rows_to_delete
                      FROM public.venta_total_snapshot_rows r
                      JOIN target t
                        ON t.id = r.snapshot_id
                    ),
                    deleted AS (
                      DELETE FROM public.venta_total_snapshots s
                      USING target t
                      WHERE s.id = t.id
                      RETURNING s.id
                    )
                    SELECT
                      (SELECT COUNT(*) FROM target) AS target_snapshots,
                      (SELECT rows_to_delete FROM target_rows) AS target_rows,
                      (SELECT COUNT(*) FROM deleted) AS deleted_snapshots
                    """
                ),
                {
                    "cutoff_date": cutoff_date,
                    "batch_limit": batch_limit,
                },
            ).mappings().one()

            deleted_snapshots = int(row["deleted_snapshots"] or 0)
            deleted_rows = int(row["target_rows"] or 0)

            db.session.commit()

            if deleted_snapshots == 0:
                break

            batches += 1
            total_deleted_snapshots += deleted_snapshots
            total_deleted_rows += deleted_rows

        return {
            "report_type_key": "venta_total",
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "dry_run": False,
            "deleted_snapshots": total_deleted_snapshots,
            "deleted_rows": total_deleted_rows,
            "batches": batches,
        }

    except Exception:
        db.session.rollback()
        raise