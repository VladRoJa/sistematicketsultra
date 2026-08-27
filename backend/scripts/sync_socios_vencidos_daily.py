from __future__ import annotations

import argparse
from datetime import date
import json

from app import create_app
from app.warehouse.services.socios_vencidos_cartera_sync_service import (
    sync_socios_vencidos_daily,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Se requiere fecha ISO YYYY-MM-DD.") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza un día de Socios Vencidos."
    )
    parser.add_argument("--business-date", required=True, type=_parse_date)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        result = sync_socios_vencidos_daily(
            business_date=args.business_date,
            requested_by="cli_sync_socios_vencidos_daily",
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
