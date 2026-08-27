from __future__ import annotations

import argparse
import json

from app import create_app
from app.warehouse.services.socios_vencidos_repository import (
    seed_socios_vencidos_cartera_from_existing_snapshots,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Puebla cartera de Socios Vencidos desde snapshots legacy."
    )
    parser.add_argument(
        "--snapshot-id",
        type=int,
        default=None,
        help="Snapshot específico; por omisión procesa todos en orden.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    app = create_app()
    with app.app_context():
        result = seed_socios_vencidos_cartera_from_existing_snapshots(
            snapshot_id=args.snapshot_id,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
