"""
Inspección read-only de cuentas publicitarias Meta.

No persiste datos.
No imprime el access token.
"""

from __future__ import annotations

import os
import sys

import requests


def main() -> int:
    token = os.getenv(
        "META_ACCESS_TOKEN",
        "",
    ).strip()

    api_version = os.getenv(
        "META_GRAPH_API_VERSION",
        "",
    ).strip()

    if not token:
        print(
            "ERROR: META_ACCESS_TOKEN "
            "no está configurado.",
            file=sys.stderr,
        )
        return 2

    if not api_version:
        print(
            "ERROR: META_GRAPH_API_VERSION "
            "no está configurado.",
            file=sys.stderr,
        )
        return 2

    api_version = api_version.lstrip("/")

    url = (
        "https://graph.facebook.com/"
        f"{api_version}/me/adaccounts"
    )

    params = {
        "fields": (
            "id,"
            "account_id,"
            "name,"
            "account_status,"
            "currency,"
            "timezone_name"
        ),
        "limit": 100,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=(10, 30),
        )
    except requests.RequestException as exc:
        print(
            "ERROR HTTP: "
            f"{exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 3

    print("=== Meta Ads · cuentas accesibles ===")
    print(f"HTTP status: {response.status_code}")
    print()

    try:
        payload = response.json()
    except ValueError:
        print(
            "ERROR: respuesta no JSON.",
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

    rows = payload.get("data", [])

    if not isinstance(rows, list):
        print(
            "ERROR: data no es una lista.",
            file=sys.stderr,
        )
        return 4

    print(f"Cuentas encontradas: {len(rows)}")
    print()

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue

        print(
            f"{index:02d}. "
            f"{row.get('id', '(sin id)')} | "
            f"{row.get('name', '(sin nombre)')}"
        )
        print(
            "    currency="
            f"{row.get('currency', '?')} "
            "timezone="
            f"{row.get('timezone_name', '?')} "
            "status="
            f"{row.get('account_status', '?')}"
        )

    print()
    print(
        "OK: inspección terminada. "
        "No se persistió información."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
