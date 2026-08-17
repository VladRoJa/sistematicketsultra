"""Sincroniza Meta Ads Insights en PostgreSQL con flujo raw-first."""

from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.integrations.meta import MetaInsightsClient
from app.services.marketing_meta_run_sync_service import (
    MarketingMetaAccount,
    sync_meta_full_run,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "La fecha debe usar formato YYYY-MM-DD."
        ) from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--account",
        action="append",
        required=True,
        help=(
            "Cuenta en formato TOKEN_ENV=act_123. "
            "Puede repetirse para una corrida multi-cuenta."
        ),
    )
    parser.add_argument("--from-date", required=True, type=_parse_date)
    parser.add_argument("--to-date", required=True, type=_parse_date)
    parser.add_argument(
        "--period-key",
        help="Por defecto META-YYYY-MM según --from-date.",
    )
    parser.add_argument("--page-limit", type=int, default=500)
    parser.add_argument("--max-pages", type=int, default=10000)
    parser.add_argument(
        "--no-canonical",
        action="store_true",
        help="Finaliza COMPLETED sin promover el run a canónico.",
    )
    return parser.parse_args()


def _load_accounts(values: list[str]) -> tuple[MarketingMetaAccount, ...]:
    accounts: list[MarketingMetaAccount] = []
    for value in values:
        token_env, separator, account_id = value.partition("=")
        token_env = token_env.strip()
        account_id = account_id.strip()
        if not separator or not token_env.startswith("META_ACCESS_TOKEN_"):
            raise ValueError(
                "--account debe usar TOKEN_ENV=act_123 y una variable "
                "META_ACCESS_TOKEN_*."
            )
        token = os.getenv(token_env, "").strip()
        if not token:
            raise ValueError(f"{token_env} no está configurado.")
        accounts.append(
            MarketingMetaAccount(
                account_id=account_id,
                access_token=token,
            )
        )
    return tuple(accounts)


def main() -> int:
    args = _parse_args()
    repo_root = BACKEND_ROOT.parent
    env_path = repo_root / ".env.docker"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    try:
        accounts = _load_accounts(args.account)
        client = MetaInsightsClient()
        period_key = (
            str(args.period_key).strip()
            if args.period_key
            else f"META-{args.from_date:%Y-%m}"
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        result = sync_meta_full_run(
            period_key=period_key,
            date_from=args.from_date,
            date_to=args.to_date,
            accounts=accounts,
            client=client,
            page_limit=args.page_limit,
            max_pages_per_account=args.max_pages,
            make_canonical_on_completed=not args.no_canonical,
        )

    print(f"run_id={result.sync_run_id}")
    print(f"status={result.status}")
    print(f"canonical={result.is_canonical}")
    print(f"accounts_completed={result.accounts_completed}")
    print(f"accounts_failed={result.accounts_failed}")
    print(f"pages_received={result.pages_received}")
    print(f"insights_received={result.insights_received}")
    print(f"insights_unique={result.insights_unique}")
    return 0 if result.status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
