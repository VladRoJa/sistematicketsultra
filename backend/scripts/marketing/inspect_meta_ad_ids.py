"""
Inspección read-only de anuncios Meta por ad_id exacto.

- Lee credenciales desde .env.docker.
- No persiste información.
- No imprime access tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--token-env",
        required=True,
        help="Variable META_ACCESS_TOKEN_* a utilizar.",
    )

    parser.add_argument(
        "--ad-id",
        action="append",
        required=True,
        dest="ad_ids",
        help=(
            "Meta ad_id exacto. "
            "Se puede repetir varias veces."
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


def to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def get_json(
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=(10, 60),
        )
    except requests.RequestException as exc:
        print(
            "ERROR HTTP: "
            f"{exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 0, {}

    try:
        payload = response.json()
    except ValueError:
        print(
            "ERROR: Meta respondió contenido no JSON.",
            file=sys.stderr,
        )
        return response.status_code, {}

    if not isinstance(payload, dict):
        return response.status_code, {}

    return response.status_code, payload


def print_meta_error(
    payload: dict[str, Any],
) -> None:
    error = payload.get("error", {})

    if not isinstance(error, dict):
        print("Meta error: respuesta desconocida")
        return

    print(
        "Meta error: "
        f"{error.get('message', '(sin mensaje)')}"
    )

    if error.get("type"):
        print(f"type:       {error.get('type')}")

    if error.get("code") is not None:
        print(f"code:       {error.get('code')}")

    if error.get("error_subcode") is not None:
        print(
            "subcode:    "
            f"{error.get('error_subcode')}"
        )


def action_map(
    value: Any,
) -> dict[str, Decimal]:
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
            "ERROR: --token-env debe ser "
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

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    base_url = (
        f"https://graph.facebook.com/{version}"
    )

    detail_fields = ",".join(
        [
            "id",
            "name",
            "account_id",
            "campaign_id",
            "adset_id",
            "status",
            "effective_status",
            "configured_status",
            "created_time",
            "updated_time",
        ]
    )

    insight_fields = ",".join(
        [
            "ad_id",
            "ad_name",
            "account_id",
            "account_name",
            "campaign_id",
            "campaign_name",
            "adset_id",
            "adset_name",
            "date_start",
            "date_stop",
            "spend",
            "reach",
            "impressions",
            "clicks",
            "actions",
        ]
    )

    print(
        "=== Meta Ads · inspección por ad_id ==="
    )
    print(
        f"Periodo: {args.from_date} "
        f"-> {args.to_date}"
    )
    print(
        f"IDs:     {len(args.ad_ids)}"
    )

    had_error = False

    for index, raw_ad_id in enumerate(
        args.ad_ids,
        start=1,
    ):
        ad_id = raw_ad_id.strip()

        print()
        print(
            "========================================"
        )
        print(
            f"[{index}] AD ID: {ad_id}"
        )
        print(
            "========================================"
        )

        if not ad_id.isdigit():
            print("ERROR: ad_id no numérico.")
            had_error = True
            continue

        detail_url = (
            f"{base_url}/{ad_id}"
        )

        detail_status, detail = get_json(
            url=detail_url,
            headers=headers,
            params={
                "fields": detail_fields,
            },
        )

        print(
            f"Detalle HTTP: {detail_status}"
        )

        if detail_status != 200:
            print_meta_error(detail)
            had_error = True
            continue

        print(
            f"name:              "
            f"{detail.get('name', '')}"
        )
        print(
            f"account_id:        "
            f"{detail.get('account_id', '')}"
        )
        print(
            f"campaign_id:       "
            f"{detail.get('campaign_id', '')}"
        )
        print(
            f"adset_id:          "
            f"{detail.get('adset_id', '')}"
        )
        print(
            f"status:            "
            f"{detail.get('status', '')}"
        )
        print(
            f"effective_status:  "
            f"{detail.get('effective_status', '')}"
        )
        print(
            f"configured_status: "
            f"{detail.get('configured_status', '')}"
        )
        print(
            f"created_time:      "
            f"{detail.get('created_time', '')}"
        )
        print(
            f"updated_time:      "
            f"{detail.get('updated_time', '')}"
        )

        insights_url = (
            f"{base_url}/{ad_id}/insights"
        )

        insight_status, insight_payload = get_json(
            url=insights_url,
            headers=headers,
            params={
                "fields": insight_fields,
                "time_range": json.dumps(
                    {
                        "since": args.from_date,
                        "until": args.to_date,
                    },
                    separators=(",", ":"),
                ),
            },
        )

        print()
        print(
            f"Insights HTTP: {insight_status}"
        )

        if insight_status != 200:
            print_meta_error(insight_payload)
            had_error = True
            continue

        data = insight_payload.get(
            "data",
            [],
        )

        if not isinstance(data, list):
            print(
                "ERROR: insights.data no es lista."
            )
            had_error = True
            continue

        if not data:
            print(
                "Sin delivery/insights "
                "en el periodo solicitado."
            )
            continue

        for row in data:
            if not isinstance(row, dict):
                continue

            print(
                f"account:  "
                f"{row.get('account_name', '')}"
            )
            print(
                f"campaign: "
                f"{row.get('campaign_name', '')}"
            )
            print(
                f"adset:    "
                f"{row.get('adset_name', '')}"
            )
            print(
                f"ad:       "
                f"{row.get('ad_name', '')}"
            )

            spend = to_decimal(
                row.get("spend")
            )

            reach = int(
                to_decimal(
                    row.get("reach")
                )
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

            print(
                f"spend:    ${spend:,.2f}"
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

            actions = action_map(
                row.get("actions")
            )

            print("actions:")

            if not actions:
                print("  (sin actions)")
            else:
                for action_type, value in sorted(
                    actions.items()
                ):
                    print(
                        f"  {action_type}: {value}"
                    )

    print()
    print(
        "OK: inspección terminada. "
        "No se persistió información."
    )

    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
