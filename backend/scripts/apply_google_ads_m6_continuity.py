"""Guarded Google Ads M6 identity continuity approval.

Default: CHECK_ONLY (read-only). --apply requires an explicit ADMICORP user id,
a previously deployed Alembic migration and fully reconciled 21604/21605 facts.

Usage in backend environment:
  python -m scripts.apply_google_ads_m6_continuity
  python -m scripts.apply_google_ads_m6_continuity --apply --approved-by-user-id <ID>
"""
from __future__ import annotations

import argparse

from app import create_app
from app.extensions import db
from app.warehouse.services.google_ads_m6_continuity_approval_service import run_approval


def main(*, apply: bool, approved_by_user_id: int | None) -> None:
    if apply and approved_by_user_id is None:
        raise ValueError("APPLY requiere --approved-by-user-id.")
    if not apply and approved_by_user_id is not None:
        raise ValueError("No indicar aprobador en CHECK_ONLY.")
    app = create_app()
    with app.app_context():
        try:
            result = run_approval(apply=apply, approved_by_user_id=approved_by_user_id)
            for key, value in result.items():
                print(f"{key.upper()} = {value}")
            print("M6_CONTINUITY_APPLY_OK" if apply else "M6_CONTINUITY_PREFLIGHT_OK")
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Explicitly approve mapped M6 continuity.")
    parser.add_argument("--approved-by-user-id", type=int, default=None)
    args = parser.parse_args()
    main(apply=args.apply, approved_by_user_id=args.approved_by_user_id)
