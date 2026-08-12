"""
Inspección read-only de Meta Ads por sucursal/nombre.

No persiste información.
No imprime el access token.
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from pathlib import Path
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--token-env",
        required=True,
        help=(
            "Nombre de la variable de entorno que contiene "
            "el token Meta."
        ),
    )

    parser.add_argument(
        "--account-id",
        required=True,
        help="ID de cuenta Meta, ej. act_123.",
    )

    parser.add_argument(
        "--search",
        required=True,
        help=(
            "Texto a buscar en campaign_name, "
            "adset_name o ad_name."
        ),
    )

    parser.add_argument(
        "--from-date",
        required=True,
        help="YYYY-MM-DD",
    )

    parser.add_argument(
        "--to-date",
        required=True,
        help="YYYY-MM-DD",
    )

    return parser.parse_args()


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()

    decomposed = unicodedata.normalize(
        "NFKD",
        text,
    )

    return "".join(
        char
        for char in decomposed
        if not unicodedata.combining(char)
    )


def to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def action_map(value: Any) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}

    if not isinstance(value, list):
        return result

    for item in value:
        if not isinstance(item, dict):
            continue

        action_type = str(
            item.get("action_type") or ""
        ).strip()

        if not action_type:
            continue

        result[action_type] = (
            result.get(
                action_type,
                Decimal("0"),
            )
            + to_decimal(item.get("value"))
        )

    return result


def main() -> int:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env.docker"

    if not env_path.exists():
        print(
            f"ERROR: no existe {env_path}",
            file=sys.stderr,
        )
        return 2

    load_dotenv(
        env_path,
        override=False,
    )

    token_env = args.token_env.strip()

    if not token_env.startswith(
        "META_ACCESS_TOKEN_"
    ):
        print(
            "ERROR: --token-env debe ser una variable "
            "META_ACCESS_TOKEN_*.",
            file=sys.stderr,
        )
        return 2

    token = os.getenv(
        token_env,
        "",
    ).strip()

    version = os.getenv(
        "META_GRAPH_API_VERSION",
        "",
    ).strip().lstrip("/")

    if not token:
        print(
            f"ERROR: {token_env} no está configurado.",
            file=sys.stderr,
        )
        return 2

    if not version:
        print(
            "ERROR: META_GRAPH_API_VERSION "
            "no está configurado.",
            file=sys.stderr,
        )
        return 2

    account_id = args.account_id.strip()

    if not account_id.startswith("act_"):
        print(
            "ERROR: --account-id debe iniciar con act_.",
            file=sys.stderr,
        )
        return 2

    url = (
        f"https://graph.facebook.com/"
        f"{version}/"
        f"{account_id}/insights"
    )

    fields = ",".join(
        [
            "account_id",
            "account_name",
            "campaign_id",
            "campaign_name",
            "adset_id",
            "adset_name",
            "ad_id",
            "ad_name",
            "spend",
            "reach",
            "impressions",
            "clicks",
            "actions",
            "date_start",
            "date_stop",
        ]
    )

    params = {
        "fields": fields,
        "level": "ad",
        "time_range": (
            '{"since":"'
            + args.from_date
            + '","until":"'
            + args.to_date
            + '"}'
        ),
        "limit": 500,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    search = normalize_text(args.search)

    rows: list[dict[str, Any]] = []

    after: str | None = None
    pages = 0

    print("=== Meta Ads · inspección por sucursal ===")
    print(f"Cuenta:   {account_id}")
    print(f"Buscar:   {args.search}")
    print(
        f"Periodo:  {args.from_date} "
        f"-> {args.to_date}"
    )
    print()

    while True:
        request_params = dict(params)

        if after:
            request_params["after"] = after

        try:
            response = requests.get(
                url,
                headers=headers,
                params=request_params,
                timeout=(10, 60),
            )
        except requests.RequestException as exc:
            print(
                "ERROR HTTP: "
                f"{exc.__class__.__name__}",
                file=sys.stderr,
            )
            return 3

        pages += 1

        print(
            f"Página {pages}: "
            f"HTTP {response.status_code}"
        )

        try:
            payload = response.json()
        except ValueError:
            print(
                "ERROR: Meta respondió no JSON.",
                file=sys.stderr,
            )
            return 4

        if response.status_code != 200:
            error = (
                payload.get("error", {})
                if isinstance(payload, dict)
                else {}
            )

            print(
                "Meta error: "
                f"{error.get('message', '(sin mensaje)')}"
            )
            return 4

        data = payload.get("data", [])

        if not isinstance(data, list):
            print(
                "ERROR: data no es lista.",
                file=sys.stderr,
            )
            return 4

        for row in data:
            if not isinstance(row, dict):
                continue

            searchable = " | ".join(
                [
                    normalize_text(
                        row.get("campaign_name")
                    ),
                    normalize_text(
                        row.get("adset_name")
                    ),
                    normalize_text(
                        row.get("ad_name")
                    ),
                ]
            )

            if search in searchable:
                rows.append(row)

        paging = payload.get("paging")

        if not isinstance(paging, dict):
            break

        cursors = paging.get("cursors")

        if not isinstance(cursors, dict):
            break

        next_after = cursors.get("after")

        if not paging.get("next") or not next_after:
            break

        after = str(next_after)

    print()
    print("=== Coincidencias ===")
    print(f"Páginas consultadas: {pages}")
    print(f"Filas encontradas:   {len(rows)}")

    if not rows:
        print()
        print(
            "NO ENCONTRADO: el texto no apareció "
            "en campaña, conjunto ni anuncio."
        )
        return 5

    total_spend = Decimal("0")
    total_impressions = 0
    total_clicks = 0

    # Reach a nivel anuncio NO lo presentamos
    # como alcance único consolidado.
    reach_rows_total = 0

    action_totals: Counter[str] = Counter()

    ad_ids: set[str] = set()
    campaigns: set[str] = set()
    adsets: set[str] = set()

    for index, row in enumerate(
        rows,
        start=1,
    ):
        ad_id = str(
            row.get("ad_id") or ""
        )

        campaign_name = str(
            row.get("campaign_name") or ""
        )

        adset_name = str(
            row.get("adset_name") or ""
        )

        ad_name = str(
            row.get("ad_name") or ""
        )

        spend = to_decimal(
            row.get("spend")
        )

        impressions = int(
            to_decimal(
                row.get("impressions")
            )
        )

        clicks = int(
            to_decimal(
                row.get("clicks")
            )
        )

        reach = int(
            to_decimal(
                row.get("reach")
            )
        )

        actions = action_map(
            row.get("actions")
        )

        if ad_id:
            ad_ids.add(ad_id)

        if campaign_name:
            campaigns.add(campaign_name)

        if adset_name:
            adsets.add(adset_name)

        total_spend += spend
        total_impressions += impressions
        total_clicks += clicks
        reach_rows_total += reach

        for action_type, value in actions.items():
            action_totals[action_type] += value

        print()
        print(f"[{index}]")
        print(
            f"campaign: {campaign_name}"
        )
        print(
            f"adset:    {adset_name}"
        )
        print(
            f"ad:       {ad_name}"
        )
        print(
            f"ad_id:    {ad_id}"
        )
        print(
            "spend:    "
            f"${spend:,.2f}"
        )
        print(
            f"reach:    {reach:,}"
        )
        print(
            f"impr.:    {impressions:,}"
        )
        print(
            f"clicks:   {clicks:,}"
        )

        if actions:
            print("actions:")

            for action_type, value in sorted(
                actions.items()
            ):
                print(
                    f"  {action_type}: {value}"
                )

    print()
    print("=== Resumen Papalote ===")
    print(
        f"Campañas distintas: {len(campaigns)}"
    )
    print(
        f"Adsets distintos:   {len(adsets)}"
    )
    print(
        f"Ads distintos:      {len(ad_ids)}"
    )
    print(
        f"Spend:              ${total_spend:,.2f}"
    )
    print(
        f"Impressions:        {total_impressions:,}"
    )
    print(
        f"Clicks:             {total_clicks:,}"
    )
    print(
        "Reach suma filas:   "
        f"{reach_rows_total:,} "
        "(no deduplicado)"
    )

    print()
    print("=== Action types acumulados ===")

    if action_totals:
        for action_type, value in (
            action_totals.most_common()
        ):
            print(
                f"{action_type}: {value}"
            )
    else:
        print("(sin actions)")

    print()
    print(
        "OK: inspección terminada. "
        "No se persistió información."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
