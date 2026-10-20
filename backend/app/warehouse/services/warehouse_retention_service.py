#   backend\app\warehouse\services\warehouse_retention_service.py


from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app import db


WAREHOUSE_LOCAL_TZ = ZoneInfo("America/Tijuana")

# Protect both direct snapshot references and row-only references. The FK
# policies on Contact Center use ON DELETE SET NULL, so retention must not
# delete snapshots still used as verification evidence.
_CONTACT_CENTER_PROTECTED_SNAPSHOT_IDS_SQL = """
  SELECT a.venta_total_snapshot_id AS snapshot_id
  FROM public.contact_center_appointments a
  WHERE a.venta_total_snapshot_id IS NOT NULL

  UNION

  SELECT r.snapshot_id
  FROM public.contact_center_appointments a
  JOIN public.venta_total_snapshot_rows r
    ON r.id = a.venta_total_snapshot_row_id

  UNION

  SELECT e.venta_total_snapshot_id AS snapshot_id
  FROM public.contact_center_appointment_result_events e
  WHERE e.venta_total_snapshot_id IS NOT NULL

  UNION

  SELECT r.snapshot_id
  FROM public.contact_center_appointment_result_events e
  JOIN public.venta_total_snapshot_rows r
    ON r.id = e.venta_total_snapshot_row_id
"""


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
    - Conserva snapshots referenciados desde citas/eventos de Contact Center.
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
                f"""
                WITH protected_snapshots AS (
                  {_CONTACT_CENTER_PROTECTED_SNAPSHOT_IDS_SQL}
                )
                SELECT
                  COUNT(DISTINCT s.id) AS target_snapshots,
                  COUNT(r.id) AS target_rows
                FROM public.venta_total_snapshots s
                LEFT JOIN public.venta_total_snapshot_rows r
                  ON r.snapshot_id = s.id
                WHERE COALESCE(s.is_canonical, false) = false
                  AND s.business_date < :cutoff_date
                  AND NOT EXISTS (
                      SELECT 1 FROM protected_snapshots p
                      WHERE p.snapshot_id = s.id
                  )
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

    # PostgreSQL READ COMMITTED is required: re-checking in a NEW statement
    # after acquiring row locks sees verification transactions that committed
    # while locks were being acquired. The existing FK SET NULL alone does not
    # preserve purchase evidence.
    try:
        for _ in range(max_batches):
            # FOR UPDATE conflicts with the FK KEY SHARE taken by new direct
            # snapshot references and by inserts of snapshot rows. SKIP LOCKED
            # keeps retention from blocking Contact Center transactions.
            candidates = db.session.execute(
                text(
                    f"""
                    WITH protected_snapshots AS (
                      {_CONTACT_CENTER_PROTECTED_SNAPSHOT_IDS_SQL}
                    )
                    SELECT s.id
                    FROM public.venta_total_snapshots s
                    WHERE COALESCE(s.is_canonical, false) = false
                      AND s.business_date < :cutoff_date
                      AND NOT EXISTS (
                          SELECT 1 FROM protected_snapshots p
                          WHERE p.snapshot_id = s.id
                      )
                    ORDER BY s.business_date, s.id
                    LIMIT :batch_limit
                    FOR UPDATE OF s SKIP LOCKED
                    """
                ),
                {"cutoff_date": cutoff_date, "batch_limit": batch_limit},
            ).mappings().all()
            candidate_ids = [int(row["id"]) for row in candidates]
            if not candidate_ids:
                db.session.commit()
                break

            # Row-only Contact Center references take FK KEY SHARE locks on
            # venta_total_snapshot_rows, not necessarily on the parent
            # snapshot. Lock EVERY existing row, or skip the whole candidate
            # when a concurrent verification holds one of its rows.
            locked_counts = {
                int(row["snapshot_id"]): int(row["locked_count"])
                for row in db.session.execute(
                    text(
                        """
                        WITH locked_rows AS (
                          SELECT r.id, r.snapshot_id
                          FROM public.venta_total_snapshot_rows r
                          WHERE r.snapshot_id = ANY(:candidate_ids)
                          ORDER BY r.snapshot_id, r.id
                          FOR UPDATE OF r SKIP LOCKED
                        )
                        SELECT snapshot_id, COUNT(*) AS locked_count
                        FROM locked_rows
                        GROUP BY snapshot_id
                        """
                    ),
                    {"candidate_ids": candidate_ids},
                ).mappings().all()
            }

            # This MUST be a fresh SQL statement after both locking stages.
            # Every selected snapshot and each of its existing rows remain
            # locked until commit, closing both direct and row-only FK races.
            verified = db.session.execute(
                text(
                    f"""
                    WITH protected_snapshots AS (
                      {_CONTACT_CENTER_PROTECTED_SNAPSHOT_IDS_SQL}
                    )
                    SELECT s.id,
                           (SELECT COUNT(*)
                            FROM public.venta_total_snapshot_rows r
                            WHERE r.snapshot_id = s.id) AS total_rows
                    FROM public.venta_total_snapshots s
                    WHERE s.id = ANY(:candidate_ids)
                      AND COALESCE(s.is_canonical, false) = false
                      AND s.business_date < :cutoff_date
                      AND NOT EXISTS (
                          SELECT 1 FROM protected_snapshots p
                          WHERE p.snapshot_id = s.id
                      )
                    """
                ),
                {"candidate_ids": candidate_ids, "cutoff_date": cutoff_date},
            ).mappings().all()

            # The row count detects FK KEY SHARE locks skipped above. Never
            # purge a snapshot if even one row was unavailable for locking.
            eligible_row_counts = {
                int(row["id"]): int(row["total_rows"])
                for row in verified
                if locked_counts.get(int(row["id"]), 0)
                == int(row["total_rows"])
            }
            if not eligible_row_counts:
                db.session.commit()
                break

            deleted = db.session.execute(
                text(
                    """
                    DELETE FROM public.venta_total_snapshots s
                    WHERE s.id = ANY(:eligible_ids)
                    RETURNING s.id
                    """
                ),
                {"eligible_ids": list(eligible_row_counts)},
            ).mappings().all()
            deleted_ids = [int(row["id"]) for row in deleted]
            deleted_snapshots = len(deleted_ids)
            deleted_rows = sum(eligible_row_counts[id] for id in deleted_ids)

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
