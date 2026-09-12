from __future__ import annotations

import json

from app import create_app
from app.demo_environment import DemoEnvironmentError, ensure_demo_branch
from app.extensions import db


def main() -> int:
    app = create_app()

    with app.app_context():
        try:
            result = ensure_demo_branch(db.session)
            db.session.commit()
        except DemoEnvironmentError as exc:
            db.session.rollback()
            print(json.dumps({"status": "error", "detail": str(exc)}, ensure_ascii=False))
            return 2
        except Exception:
            db.session.rollback()
            raise

        print(
            json.dumps(
                {
                    "status": "ok",
                    "demo_branch": result.to_dict(),
                },
                ensure_ascii=False,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
