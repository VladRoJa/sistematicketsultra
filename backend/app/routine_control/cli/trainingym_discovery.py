from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.routine_control.providers.trainingym import TrainingymDiscoveryService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Descubrimiento sanitizado del portal Trainingym.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", dest="headless")
    mode.add_argument("--headed", action="store_false", dest="headless")
    parser.set_defaults(headless=None)
    parser.add_argument("--diagnostic-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = TrainingymDiscoveryService().run(
        headless=args.headless,
        diagnostic_dir=args.diagnostic_dir,
    )
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
        print(f"succeeded={str(result.succeeded).lower()}")
        print(f"post_login_path={result.post_login_path or ''}")
        print(f"visible_controls={len(result.visible_controls)}")
        print(f"diagnostic_artifact={result.diagnostic_artifact or ''}")
        if result.error_code:
            print(f"error_code={result.error_code}")
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())

