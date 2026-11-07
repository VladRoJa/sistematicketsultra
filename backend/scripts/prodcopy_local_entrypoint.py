"""Guarded entrypoint for a local copy of production data.

The Compose environment inherits existing DB credentials only to authenticate
with the *local* PostgreSQL container. No production URL or signing keys are
allowed to be reused by this dev backend.
"""

from __future__ import annotations

import os
import secrets
import sys

from sqlalchemy.engine import make_url


TARGET_DATABASE = "suiteultra_dev_prodcopy"
TARGET_HOST = "prodcopy-db"


def main() -> None:
    if os.environ.get("SUITE_PRODCOPY_LOCAL_ONLY") != "true":
        raise SystemExit("Refusing to start: SUITE_PRODCOPY_LOCAL_ONLY is required.")

    if len(sys.argv) < 2:
        raise SystemExit("Usage: prodcopy_local_entrypoint.py <command> [args...]")

    source_uri = os.environ.get("SQLALCHEMY_DATABASE_URI", "")
    try:
        source = make_url(source_uri)
    except Exception as exc:
        raise SystemExit("Invalid PostgreSQL configuration for local DB.") from exc

    # Refuse any remote DB URL, even if .env.docker was inadvertently changed.
    if (
        source.get_backend_name() != "postgresql"
        or source.host not in {"db", "sistematickets-db-1"}
        or source.database != "sistema_tickets"
    ):
        raise SystemExit(
            "Refusing to start: expected local PostgreSQL source "
            "db/sistema_tickets. No remote database is allowed."
        )

    local = source.set(host=TARGET_HOST, database=TARGET_DATABASE)
    os.environ["SQLALCHEMY_DATABASE_URI"] = local.render_as_string(
        hide_password=False
    )
    # These values are intentionally ephemeral and do not reuse production keys.
    # Existing browser sessions expire on a local backend restart.
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
    os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
    os.environ["APP_ENV"] = "local"
    os.environ["AUTH_REFRESH_ENABLED"] = "false"

    # Defense in depth, in addition to the backend's internal-only Docker net.
    for name in (
        "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED",
        "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY",
        "CAMPAIGN_V2_PROVIDER_SEND_ENABLED",
        "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED",
        "CAMPAIGN_V2_PROVIDER_STATS_AUTO_CAPTURE_ENABLED",
        "MARKETING_SCHEDULER_ENABLED",
        "TRACK_SCHEDULER_ENABLED",
        "REPORTS_SCHEDULER_ENABLED",
        "ROUTINE_CONTROL_SCHEDULER_ENABLED",
    ):
        os.environ[name] = "false"

    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)


if __name__ == "__main__":
    main()
