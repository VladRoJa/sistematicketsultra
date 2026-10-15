"""Read-only Google Ads M6 continuity preflight.

The CLI deliberately does NOT expose --apply or --approved-by-user-id:
passing an existing ADMICORP ID cannot authenticate the shell operator.
Production approval requires a future authenticated backend workflow.

Usage: python -m scripts.apply_google_ads_m6_continuity
"""
from __future__ import annotations

import argparse

from app import create_app
from app.extensions import db
from app.warehouse.services.google_ads_m6_continuity_approval_service import run_approval


def main() -> None:
    app = create_app()
    with app.app_context():
        try:
            result = run_approval()
            for key, value in result.items():
                print(f"{key.upper()} = {value}")
            print("M6_CONTINUITY_PREFLIGHT_OK")
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()  # reject --apply rather than silently ignoring it
    main()
