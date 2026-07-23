from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from typing import Callable, Sequence

from app import create_app
from app.routine_control.pipeline.automated_pipeline_service import (
    run_automated_routine_control_pipeline,
)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Debe ser una fecha YYYY-MM-DD válida.") from exc


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Debe ser un datetime ISO8601 válido.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "El datetime ISO8601 debe incluir timezone."
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline automatizado de providers de Control de Rutinas.",
    )
    parser.add_argument("--date-from", required=True, type=_date)
    parser.add_argument("--date-to", required=True, type=_date)
    parser.add_argument("--observed-at-utc", required=True, type=_aware_datetime)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", dest="headless")
    mode.add_argument("--headed", action="store_false", dest="headless")
    parser.set_defaults(headless=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    app_factory: Callable[[], object] = create_app,
    pipeline_service: Callable[..., object] = run_automated_routine_control_pipeline,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        app = app_factory()
        with app.app_context():
            result = pipeline_service(
                date_from=args.date_from,
                date_to=args.date_to,
                observed_at_utc=args.observed_at_utc,
                headless=args.headless,
            )
    except Exception as exc:
        payload = {
            "error_code": "AUTOMATED_CLI_FAILED",
            "error_message": type(exc).__name__,
            "status": "FAILED",
            "succeeded": False,
        }
        if args.as_json:
            print(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        else:
            print("succeeded=false")
            print("error_code=AUTOMATED_CLI_FAILED")
        return 1

    if args.as_json:
        print(
            json.dumps(
                result.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        print(f"status={result.status}")
        print(f"succeeded={str(result.succeeded).lower()}")
        print(f"error_code={result.error_code or ''}")
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())

