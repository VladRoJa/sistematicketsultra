from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from app import create_app
from app.routine_control.pipeline.manual_pipeline_service import (
    run_manual_routine_control_pipeline,
)


def _existing_file(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError("El archivo indicado no existe.")
    return path


def _aware_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Debe ser un datetime ISO8601 válido."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "El datetime ISO8601 debe incluir timezone."
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline manual de Control de Rutinas.",
    )
    parser.add_argument("--gasca-xlsx", required=True, type=_existing_file)
    parser.add_argument("--trainingym-xlsx", required=True, type=_existing_file)
    parser.add_argument(
        "--observed-at-utc",
        required=True,
        type=_aware_datetime,
    )
    parser.add_argument("--requested-by")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _print_plain(result) -> None:
    print(f"pipeline_run_id={result.pipeline_run_id}")
    print(f"succeeded={str(result.succeeded).lower()}")
    print(
        "gasca="
        f"source:{result.gasca_source_rows},"
        f"accepted:{result.gasca_accepted},"
        f"rejected:{result.gasca_rejected}"
    )
    print(
        "trainingym="
        f"source:{result.trainingym_source_rows},"
        f"accepted:{result.trainingym_accepted},"
        f"rejected:{result.trainingym_rejected}"
    )
    print(
        f"members={result.members_created + result.members_updated},"
        f"evidences={result.evidences_created + result.evidences_updated},"
        f"links={result.links_created + result.links_existing},"
        f"incidents={result.incidents_created}"
    )
    print(
        "status_counts="
        + json.dumps(dict(result.status_counts), sort_keys=True)
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        app = create_app()
        with app.app_context():
            result = run_manual_routine_control_pipeline(
                gasca_xlsx=args.gasca_xlsx,
                trainingym_xlsx=args.trainingym_xlsx,
                observed_at_utc=args.observed_at_utc,
                requested_by=args.requested_by,
            )
    except Exception as exc:
        print(
            f"manual_pipeline_failed={type(exc).__name__}",
            file=sys.stderr,
        )
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
        _print_plain(result)
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
