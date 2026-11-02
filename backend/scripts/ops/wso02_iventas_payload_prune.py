"""WSO-02: preview / owner-approved pruning of superseded iVentas payload.

Preserves sync run records and persisted counters. Removes only raw pages,
contacts and tags of COMPLETED noncanonical runs superseded for the SAME cutoff,
with no Contact Center source-row link. Bounded transaction per run.

No operation is performed on production by committing/deploying this script.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
import shutil
from pathlib import Path

from sqlalchemy import text
from app import create_app
from app.extensions import db

CANDIDATE_SQL = """
SELECT r.id, r.period_key, r.date_from, r.date_to, r.contacts_unique,
       (SELECT COUNT(*) FROM public.marketing_iventas_contacts c
        WHERE c.sync_run_id = r.id) AS contact_rows,
       (SELECT COUNT(*) FROM public.marketing_iventas_contact_tags t
        WHERE t.sync_run_id = r.id) AS tag_rows,
       (SELECT COUNT(*) FROM public.marketing_iventas_raw_pages p
        WHERE p.sync_run_id = r.id) AS raw_pages
FROM public.marketing_iventas_sync_runs r
WHERE r.status = 'COMPLETED'
  AND r.is_canonical = false
  AND r.payload_pruned_at IS NULL
  AND EXISTS (
    SELECT 1 FROM public.marketing_iventas_sync_runs newer
    WHERE newer.period_key = r.period_key
      AND newer.date_from = r.date_from
      AND newer.date_to = r.date_to
      AND newer.status = 'COMPLETED'
      AND newer.id > r.id
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.contact_center_contact_links cc
    JOIN public.marketing_iventas_contacts c ON c.id = cc.source_row_id
    WHERE cc.source_type = 'IVENTAS_CONTACT'
      AND c.sync_run_id = r.id
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.marketing_reactivation_campaigns m
    WHERE m.filters_json -> 'sources' ->> 'iventas_sync_run_id' = r.id::text
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.marketing_campaign_v2_campaigns v
    WHERE COALESCE(
      v.audience_definition_json -> 'source_metadata' ->> 'iventas_sync_run_id',
      v.audience_definition_json -> 'sources' ->> 'iventas_sync_run_id'
    ) = r.id::text
  )
ORDER BY r.id
"""

ELIGIBLE_SQL = """
SELECT r.id FROM public.marketing_iventas_sync_runs r
WHERE r.id = :id AND r.status = 'COMPLETED'
  AND r.is_canonical = false AND r.payload_pruned_at IS NULL
  AND EXISTS (
    SELECT 1 FROM public.marketing_iventas_sync_runs newer
    WHERE newer.period_key = r.period_key
      AND newer.date_from = r.date_from
      AND newer.date_to = r.date_to
      AND newer.status = 'COMPLETED'
      AND newer.id > r.id
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.contact_center_contact_links cc
    JOIN public.marketing_iventas_contacts c ON c.id = cc.source_row_id
    WHERE cc.source_type = 'IVENTAS_CONTACT'
      AND c.sync_run_id = r.id
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.marketing_reactivation_campaigns m
    WHERE m.filters_json -> 'sources' ->> 'iventas_sync_run_id' = r.id::text
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.marketing_campaign_v2_campaigns v
    WHERE COALESCE(
      v.audience_definition_json -> 'source_metadata' ->> 'iventas_sync_run_id',
      v.audience_definition_json -> 'sources' ->> 'iventas_sync_run_id'
    ) = r.id::text
  )
"""

CHILD_TABLES = (
    ("tag_rows", "marketing_iventas_contact_tags"),
    ("contact_rows", "marketing_iventas_contacts"),
    ("raw_pages", "marketing_iventas_raw_pages"),
)


def _counts(conn, run_id: int) -> dict[str, int]:
    return {
        label: int(conn.execute(text(
            f"SELECT COUNT(*) FROM public.{table} WHERE sync_run_id = :id"
        ), {"id": run_id}).scalar_one())
        for label, table in CHILD_TABLES
    }


def _manifest_rows(conn) -> list[dict]:
    rows = conn.execute(text(CANDIDATE_SQL)).mappings().all()
    return [
        {
            "id": int(row["id"]),
            "period_key": str(row["period_key"]),
            "date_from": row["date_from"].isoformat(),
            "date_to": row["date_to"].isoformat(),
            "contact_rows": int(row["contact_rows"]),
            "tag_rows": int(row["tag_rows"]),
            "raw_pages": int(row["raw_pages"]),
        }
        for row in rows
    ]


def _read_manifest(path: Path) -> list[dict]:
    content = json.loads(path.read_text(encoding="utf-8"))
    if content.get("operation") != "wso02_superseded_payload_prune_v1":
        raise RuntimeError("WSO-02 blocked: unexpected manifest identity")
    items = content.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("WSO-02 blocked: manifest missing candidate rows")
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("WSO-02 blocked: malformed run entry")
        run_id = item.get("id")
        if type(run_id) is not int or run_id <= 0 or run_id in seen:
            raise RuntimeError("WSO-02 blocked: invalid/duplicate run ID")
        seen.add(run_id)
        if not isinstance(item.get("period_key"), str):
            raise RuntimeError("WSO-02 blocked: invalid period")
        for field in ("date_from", "date_to"):
            if not isinstance(item.get(field), str):
                raise RuntimeError("WSO-02 blocked: invalid cutoff")
            date.fromisoformat(item[field])
        for key, _ in CHILD_TABLES:
            if type(item.get(key)) is not int or item[key] < 0:
                raise RuntimeError("WSO-02 blocked: invalid child count")
    return items


def _manifest_path(value: Path) -> Path:
    if not value.is_absolute() or "private" not in value.parts or "uploads" in value.parts:
        raise RuntimeError("WSO-02 blocked: manifest must be absolute and private")
    if value.is_symlink() or value.parent.is_symlink():
        raise RuntimeError("WSO-02 blocked: manifest path cannot be symlinked")
    return value


def _prune_one(conn, item: dict) -> str:
    """One complete transaction per run; caller must use engine.begin()."""
    conn.exec_driver_sql("SET LOCAL lock_timeout = '3s'")
    conn.exec_driver_sql("SET LOCAL statement_timeout = '120s'")
    run_id = int(item["id"])
    run = conn.execute(text("""
        SELECT id, period_key, date_from, date_to, payload_pruned_at
        FROM public.marketing_iventas_sync_runs
        WHERE id = :id FOR UPDATE
    """), {"id": run_id}).mappings().one_or_none()
    if run is None:
        raise RuntimeError(f"WSO-02 blocked: run {run_id} disappeared")
    identity = (str(run["period_key"]), run["date_from"].isoformat(),
                run["date_to"].isoformat())
    if identity != (item["period_key"], item["date_from"], item["date_to"]):
        raise RuntimeError(f"WSO-02 blocked: run {run_id} identity changed")
    if run["payload_pruned_at"] is not None:
        if any(_counts(conn, run_id).values()):
            raise RuntimeError(f"WSO-02 blocked: run {run_id} partly pruned")
        return "already_pruned"

    # SHARE locks prevent creating a new implicit reference while pruning.
    # SELECT readers remain available. The locks are transaction scoped.
    conn.exec_driver_sql(
        "LOCK TABLE public.contact_center_contact_links, "
        "public.marketing_campaign_v2_campaigns, "
        "public.marketing_reactivation_campaigns IN SHARE MODE"
    )
    if conn.execute(text(ELIGIBLE_SQL), {"id": run_id}).scalar_one_or_none() is None:
        raise RuntimeError(f"WSO-02 blocked: run {run_id} no longer eligible")

    counts = _counts(conn, run_id)
    for key, _ in CHILD_TABLES:
        if counts[key] != item[key]:
            raise RuntimeError(
                f"WSO-02 blocked: run {run_id} {key} changed "
                f"(expected {item[key]}, observed {counts[key]})"
            )

    # Tags first: avoid implicitly cascading millions of tag deletes
    # while deleting the contact rows. Then RAW pages and marker.
    for key, table in CHILD_TABLES:
        result = conn.execute(text(
            f"DELETE FROM public.{table} WHERE sync_run_id = :id"
        ), {"id": run_id})
        if result.rowcount != item[key]:
            raise RuntimeError(
                f"WSO-02 blocked: run {run_id} {key} delete count mismatch"
            )
    updated = conn.execute(text("""
        UPDATE public.marketing_iventas_sync_runs
        SET payload_pruned_at = CURRENT_TIMESTAMP
        WHERE id = :id AND payload_pruned_at IS NULL
    """), {"id": run_id})
    if updated.rowcount != 1:
        raise RuntimeError(f"WSO-02 blocked: run {run_id} mark failed")
    return "pruned"


def _apply_items(
    *,
    engine,
    items: list[dict],
    manifest_parent: Path,
    max_runs: int,
    min_free_gb: int,
) -> dict[str, int]:
    """Process at most max_runs *new* runs, skipping earlier completed runs.

    The same immutable manifest can be reused for each bounded batch.
    A failed run aborts the current invocation; prior run transactions stay
    committed and future invocations resume after them.
    """
    completed = 0
    already = 0
    considered = 0
    for item in items:
        if completed >= max_runs:
            break
        free = shutil.disk_usage(manifest_parent).free
        if free < min_free_gb * 1024 ** 3:
            raise RuntimeError(
                "WSO-02 blocked: disk headroom below the configured "
                f"{min_free_gb} GiB threshold"
            )
        with engine.begin() as conn:
            state = _prune_one(conn, item)
        considered += 1
        if state == "pruned":
            completed += 1
            print(json.dumps({
                "run_id": item["id"], "state": state,
                "completed": completed,
            }), flush=True)
        elif state == "already_pruned":
            already += 1
        else:
            raise RuntimeError("WSO-02 blocked: unexpected pruning state")
    return {
        "runs_pruned": completed,
        "runs_already_pruned": already,
        "runs_remaining_in_manifest": len(items) - considered,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("preview", "apply"))
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--apply", action="store_true", help="Required for irreversible deletion")
    p.add_argument("--ack-irreversible", action="store_true")
    p.add_argument("--max-runs", type=int, default=0,
                   help="Mandatory upper bound of runs per execution when applying")
    p.add_argument("--min-free-gb", type=int, default=30,
                   help="Abort if manifest filesystem has less than this many GiB free")
    args = p.parse_args()
    manifest = _manifest_path(args.manifest)
    app = create_app()
    with app.app_context():
        if args.mode == "preview":
            if manifest.exists():
                raise RuntimeError("WSO-02 blocked: manifest already exists")
            with db.engine.connect() as conn:
                conn.exec_driver_sql("SET LOCAL statement_timeout = '180s'")
                items = _manifest_rows(conn)
                conn.rollback()
            if not items:
                print(json.dumps({"mode": "preview", "runs": 0, "contacts": 0}))
                return
            manifest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            manifest.parent.chmod(0o700)
            fd = os.open(
                manifest,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            data = {
                "operation": "wso02_superseded_payload_prune_v1",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "items": items,
            }
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(data, out, indent=2)
                out.write("\n")
            print(json.dumps({
                "mode": "preview", "runs": len(items),
                "contacts": sum(i["contact_rows"] for i in items),
                "tags": sum(i["tag_rows"] for i in items),
                "raw_pages": sum(i["raw_pages"] for i in items),
            }))
            return

        if not (args.apply and args.ack_irreversible and args.max_runs > 0):
            raise RuntimeError(
                "WSO-02 blocked: --apply --ack-irreversible and "
                "--max-runs N required"
            )
        if args.min_free_gb < 20:
            raise RuntimeError("WSO-02 blocked: minimum free space must be at least 20 GiB")
        items = _read_manifest(manifest)
        summary = _apply_items(
            engine=db.engine,
            items=items,
            manifest_parent=manifest.parent,
            max_runs=args.max_runs,
            min_free_gb=args.min_free_gb,
        )
        print(json.dumps({"mode": "apply", **summary}))


if __name__ == "__main__":
    main()
