"""Run M2 sale-month validation manually in a worker-capable Flask environment.

EXAMPLE:
  python -m scripts.campaign_v2_m2_sales_month_readonly \
      --from-date 2026-10-01 --to-date 2026-10-31 --window-days 14

Read-only queries only. Prints no phone numbers, sales rows or names. It does
not schedule itself or modify the UI/flags. Pending evidence exits non-zero.
"""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from app import create_app
from app.extensions import db
from app.services.marketing_campaign_v2_sales_month_source_service import (
    UniqueSalesEvidenceError,
    reconcile_sale_month,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="M2 audit: income after proven iVentas sends by sale month (read-only)."
    )
    parser.add_argument("--from-date", required=True, help="YYYY-MM-DD, first sale day")
    parser.add_argument("--to-date", required=True, help="YYYY-MM-DD, last sale day")
    parser.add_argument("--window-days", required=True, type=int, choices=(7, 14, 30))
    args = parser.parse_args(argv)
    app = create_app()
    with app.app_context():
        try:
            result = reconcile_sale_month(
                from_date=args.from_date,
                to_date=args.to_date,
                window_days=args.window_days,
                session=db.session,
            )
        except UniqueSalesEvidenceError as exc:
            result = {"status": "INVALID_REQUEST", "reason": str(exc)}
        finally:
            db.session.remove()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
