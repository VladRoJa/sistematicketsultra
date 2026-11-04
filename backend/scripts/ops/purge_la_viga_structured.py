"""One-time purge of cancelled LA VIGA structured rows.

Deliberately retains national Warehouse RAW uploads and snapshot headers:
the underlying files contain other branches and their checksums must remain
unchanged. Parsed-row counts on headers are ingestion-time statistics.

Usage:
  python backend/scripts/ops/purge_la_viga_structured.py
  python backend/scripts/ops/purge_la_viga_structured.py --commit
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from app import create_app
from app.extensions import db


# Exact production preflight provided by the operator on 2026-11-04.
# Refuse to delete if the current dataset differs from the reviewed scope.
EXPECTED_COUNTS = {
    "venta_total_snapshot_rows": 4,
    "kpi_desempeno_snapshot_rows": 178,
    "kpi_ventas_nuevos_socios_snapshot_rows": 177,
    "reporte_direccion_snapshot_rows": 178,
    "cargos_recurrentes_snapshot_rows": 0,
}
NORMALIZED_BRANCH_PREDICATE = (
    "regexp_replace(UPPER(BTRIM(sucursal)), '[^A-Z0-9]+', '_', 'g') "
    "= 'LA_VIGA'"
)


def _count_rows(table: str) -> int:
    # Whitelist table names: identifiers cannot be bound as SQL parameters.
    if table not in EXPECTED_COUNTS:
        raise ValueError(f"Unexpected table: {table}")
    return int(
        db.session.execute(
            text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE {NORMALIZED_BRANCH_PREDICATE}"
            )
        ).scalar_one()
    )


def _reference_counts() -> dict[str, int]:
    # Both known foreign keys have ON DELETE SET NULL. Don't silently
    # detach Contact Center verification evidence from the deleted sale.
    target = (
        "SELECT id FROM venta_total_snapshot_rows "
        f"WHERE {NORMALIZED_BRANCH_PREDICATE}"
    )
    return {
        table: int(
            db.session.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE venta_total_snapshot_row_id "
                    f"IN ({target})"
                )
            ).scalar_one()
        )
        for table in (
            "contact_center_appointments",
            "contact_center_appointment_result_events",
        )
    }


def purge(*, commit: bool) -> dict:
    before = {table: _count_rows(table) for table in EXPECTED_COUNTS}
    references = _reference_counts()
    report = {
        "mode": "COMMIT" if commit else "DRY_RUN",
        "expected": EXPECTED_COUNTS,
        "before": before,
        "contact_center_references": references,
        "deleted": {},
    }

    if not commit:
        db.session.rollback()
        return report

    if before != EXPECTED_COUNTS:
        raise RuntimeError(
            "The production counts changed since the reviewed preflight; "
            "aborting: " + json.dumps(report, sort_keys=True)
        )

    if any(references.values()):
        raise RuntimeError(
            "Contact Center purchase evidence points to LA VIGA sales; "
            "refusing to detach it: " + json.dumps(report, sort_keys=True)
        )

    for table, expected in EXPECTED_COUNTS.items():
        deleted = db.session.execute(
            text(
                f"DELETE FROM {table} "
                f"WHERE {NORMALIZED_BRANCH_PREDICATE}"
            )
        ).rowcount
        report["deleted"][table] = int(deleted or 0)
        if deleted != expected:
            raise RuntimeError(
                f"Concurrent change deleting {table}: "
                f"expected {expected}, deleted {deleted}"
            )

    remaining = {
        table: _count_rows(table) for table in EXPECTED_COUNTS
    }
    if any(remaining.values()):
        raise RuntimeError(
            "Some cancelled branch rows remain: "
            + json.dumps(remaining, sort_keys=True)
        )

    db.session.commit()
    report["remaining"] = remaining
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        try:
            report = purge(commit=args.commit)
        except Exception:
            db.session.rollback()
            raise

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
