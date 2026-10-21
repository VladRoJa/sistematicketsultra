"""Backfill mensual y reanudable de Meta Ads Insights, sin promoción canónica.

Simulación por defecto. En ejecución procesa como máximo un mes nuevo por
invocación, salvo que el operador amplíe explícitamente --max-months.
El mes corriente se reserva al marketing-scheduler.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime
import os
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.integrations.meta import MetaInsightsClient
from app.models.marketing import MarketingMetaSyncRunORM
from app.services.marketing_meta_run_sync_service import (
    MarketingMetaAccount,
    sync_meta_full_run,
)
from app.services.marketing_scheduler_worker import DEFAULT_META_ACCOUNT_BINDINGS


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Fecha inválida; use YYYY-MM-DD") from exc


def month_windows(start: date, end: date):
    """Produce cortes mensuales inclusivos, con bordes parciales."""
    if start > end:
        raise ValueError("from-date debe ser <= to-date")
    current = start.replace(day=1)
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        month_end = current.replace(day=last_day)
        yield (
            current.strftime("META-%Y-%m"),
            max(start, current),
            min(end, month_end),
        )
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def classify_runs(runs, *, start: date, end: date, account_count: int) -> str:
    """No considera recuperado un rango o universo de cuentas distinto."""
    if any(run.status == "RUNNING" for run in runs):
        return "BLOCK_RUNNING"
    for run in runs:
        if run.is_canonical:
            if run.date_from != start or run.date_to != end:
                return "BLOCK_CANONICAL_RANGE"
            if (
                run.status != "COMPLETED"
                or run.accounts_requested != account_count
                or run.accounts_completed != account_count
                or run.accounts_failed != 0
            ):
                return "BLOCK_CANONICAL_ACCOUNTS"
            return "SKIP_CANONICAL"
    for run in runs:
        if (
            run.status == "COMPLETED"
            and run.date_from == start
            and run.date_to == end
            and run.accounts_requested == account_count
            and run.accounts_completed == account_count
            and run.accounts_failed == 0
        ):
            return "SKIP_COMPLETED"
    return "PENDING"


def read_month_state(period: str, start: date, end: date, account_count: int):
    rows = (
        MarketingMetaSyncRunORM.query.filter_by(period_key=period)
        .order_by(MarketingMetaSyncRunORM.id.desc())
        .all()
    )
    return classify_runs(
        rows, start=start, end=end, account_count=account_count
    )


def load_accounts() -> tuple[MarketingMetaAccount, ...]:
    accounts = []
    for token_key, account_key in DEFAULT_META_ACCOUNT_BINDINGS:
        token = os.getenv(token_key, "").strip()
        account_id = os.getenv(account_key, "").strip()
        if not token or not account_id:
            raise ValueError(
                f"Configuración Meta incompleta para {account_key}"
            )
        accounts.append(
            MarketingMetaAccount(account_id=account_id, access_token=token)
        )
    account_ids = [a.account_id.removeprefix("act_") for a in accounts]
    if len(account_ids) != len(set(account_ids)):
        raise ValueError("Cuentas Meta duplicadas en configuración")
    return tuple(accounts)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", type=parse_date, required=True)
    parser.add_argument("--to-date", type=parse_date, required=True)
    parser.add_argument(
        "--execute", action="store_true",
        help="Permite escritura en PostgreSQL y consultas a Meta",
    )
    parser.add_argument(
        "--max-months", type=int, default=1,
        help="Máximo de periodos nuevos a procesar (default: 1)",
    )
    parser.add_argument(
        "--pause-seconds", type=float, default=3.0,
        help="Pausa entre periodos nuevos (default: 3)",
    )
    parser.add_argument("--page-limit", type=int, default=500)
    parser.add_argument("--max-pages", type=int, default=10000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    today = datetime.now(
        ZoneInfo("America/Tijuana")
    ).date()
    if args.from_date > args.to_date or args.to_date > today:
        print("ERROR: intervalo inválido o fecha futura", file=sys.stderr)
        return 2
    if (
        args.max_months < 1 or args.pause_seconds < 0
        or not (1 <= args.page_limit <= 500) or args.max_pages < 1
    ):
        print("ERROR: límites inválidos", file=sys.stderr)
        return 2

    env_file = BACKEND_ROOT.parent / ".env.docker"
    if env_file.exists():
        load_dotenv(env_file, override=False)

    try:
        accounts = load_accounts() if args.execute else ()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    account_count = len(DEFAULT_META_ACCOUNT_BINDINGS)
    app = create_app()
    windows = list(month_windows(args.from_date, args.to_date))
    attempted = completed = skipped = pending = 0
    print(
        f"MODE={'EXECUTE' if args.execute else 'DRY_RUN'} "
        f"MONTHS={len(windows)} ACCOUNTS={account_count} "
        f"MAX_NEW_MONTHS={args.max_months}",
        flush=True,
    )

    with app.app_context():
        try:
            for period, start, end in windows:
                if start.replace(day=1) == today.replace(day=1):
                    print(f"{period} SKIP_ACTIVE_MONTH scheduler_owner", flush=True)
                    skipped += 1
                    continue

                state = read_month_state(period, start, end, account_count)
                if state.startswith("BLOCK_"):
                    print(f"{period} {state} range={start}:{end}", flush=True)
                    return 3
                if state.startswith("SKIP_"):
                    skipped += 1
                    print(f"{period} {state} range={start}:{end}", flush=True)
                    continue

                pending += 1
                if not args.execute:
                    print(f"{period} PENDING range={start}:{end}", flush=True)
                    continue
                if attempted >= args.max_months:
                    print("HALT_MAX_MONTHS reached", flush=True)
                    break
                if attempted and args.pause_seconds:
                    time.sleep(args.pause_seconds)
                attempted += 1
                print(f"{period} START range={start}:{end}", flush=True)
                try:
                    result = sync_meta_full_run(
                        period_key=period,
                        date_from=start,
                        date_to=end,
                        accounts=accounts,
                        client=MetaInsightsClient(),
                        page_limit=args.page_limit,
                        max_pages_per_account=args.max_pages,
                        make_canonical_on_completed=False,
                    )
                except Exception as exc:
                    print(
                        f"{period} ERROR_TYPE={type(exc).__name__} "
                        "STOP_FOR_REVIEW",
                        file=sys.stderr, flush=True,
                    )
                    return 1
                print(
                    f"{period} RUN_ID={result.sync_run_id} "
                    f"STATUS={result.status} "
                    f"ACCOUNTS={result.accounts_completed}/{result.accounts_requested} "
                    f"PAGES={result.pages_received} "
                    f"INSIGHTS={result.insights_unique} "
                    f"CANONICAL={result.is_canonical}",
                    flush=True,
                )
                if result.status != "COMPLETED" or result.is_canonical:
                    print(f"{period} STOP_FOR_REVIEW", flush=True)
                    return 1
                completed += 1
        finally:
            db.session.remove()

    print(
        f"SUMMARY new_completed={completed} skipped={skipped} "
        f"pending_seen={pending}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
