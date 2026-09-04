from __future__ import annotations

import argparse
from datetime import date
import json

from app import create_app
from app.warehouse.services.socios_vencidos_cartera_sync_service import (
    SociosVencidosCarteraSyncError,
    backfill_socios_vencidos_cartera,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Se requiere fecha ISO YYYY-MM-DD.") from exc


def _serialize_range(value: tuple[date, date] | None):
    if value is None:
        return None
    return {"date_from": value[0].isoformat(), "date_to": value[1].isoformat()}


def _serialize_failure(value):
    return {
        "date_from": value.date_from.isoformat(),
        "date_to": value.date_to.isoformat(),
        "error": value.error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill mensual de la cartera de Socios Vencidos."
    )
    parser.add_argument("--date-from", required=True, type=_parse_date)
    parser.add_argument("--date-to", required=True, type=_parse_date)
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continúa con el siguiente mes y reporta todos los fallos al final.",
    )
    args = parser.parse_args()

    app = create_app()
    try:
        with app.app_context():
            result = backfill_socios_vencidos_cartera(
                date_from=args.date_from,
                date_to=args.date_to,
                requested_by="cli_backfill_socios_vencidos",
                continue_on_error=args.continue_on_error,
            )
    except SociosVencidosCarteraSyncError as exc:
        print(json.dumps({
            "status": "failed",
            "last_successful_range": _serialize_range(exc.last_successful_range),
            "failed_range": _serialize_range(exc.failed_range),
            "error": str(exc),
        }, ensure_ascii=False, sort_keys=True))
        return 1

    payload = {
        "date_from": result.date_from.isoformat(),
        "date_to": result.date_to.isoformat(),
        "chunks_processed": result.chunks_processed,
        "chunks_failed": result.chunks_failed,
        "last_successful_range": _serialize_range(
            result.last_successful_range
        ),
        "failed_ranges": [
            _serialize_failure(failure) for failure in result.failed_ranges
        ],
        "cleanup_warnings": list(result.cleanup_warnings),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 1 if args.continue_on_error and result.chunks_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
