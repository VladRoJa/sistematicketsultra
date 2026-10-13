"""Load the explicitly approved M5 Google Ads branch identities.

By default: read-only preflight. --apply requires explicit operator action.
Runs after schema migration, never as part of flask db upgrade.

Usage:
  python -m scripts.apply_google_ads_m5_approved_identities
  python -m scripts.apply_google_ads_m5_approved_identities --apply
"""
from __future__ import annotations

import argparse

from app import create_app
from app.extensions import db
from app.warehouse.services.google_ads_m5_identity_seed_service import run_seed


def main(*, apply: bool) -> None:
    app = create_app()
    with app.app_context():
        try:
            result = run_seed(apply=apply)
            for key, value in result.items():
                print(f"{key.upper()} = {value}")
            print("M5_IDENTITY_APPLY_OK" if apply else "M5_IDENTITY_PREFLIGHT_OK")
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Google Ads M5 approved historical mapping: read-only by default"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Explicitly commit 26 mappings after successful preflight",
    )
    args = parser.parse_args()
    main(apply=args.apply)
