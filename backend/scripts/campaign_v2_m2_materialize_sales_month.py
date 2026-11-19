"""Explicit M2 materialization entrypoint, never auto-enabled or called by Flask.

After applicable Alembic migration, an authorized operator can run this
off the web worker. It reads canonical Venta Total and persisted iVentas
provider observations and writes *aggregate-only* monthly cache rows.

Example (from backend/):
 python -m scripts.campaign_v2_m2_materialize_sales_month \
   --from-date 2026-10-01 --to-date 2026-10-31 --window-days 14 \
   --write-materialized-cache

This command cannot send campaigns or call an external provider.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Sequence

from app import create_app
from app.extensions import db
from app.services.marketing_campaign_v2_sales_month_materialization_service import (
    materialize_sale_month,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update no-phone M2 commercial cache after the canonical cutoff."
    )
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--window-days", required=True, type=int, choices=(7, 14, 30))
    parser.add_argument("--write-materialized-cache", required=True, action="store_true")
    args = parser.parse_args(argv)
    app = create_app()
    with app.app_context():
        try:
            result = materialize_sale_month(
                from_date=args.from_date,
                to_date=args.to_date,
                window_days=args.window_days,
                checked_at=datetime.now(timezone.utc),
                session=db.session,
            )
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
