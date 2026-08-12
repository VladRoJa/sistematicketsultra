"""
Inspección read-only de contactos iVentas por tag ad_fb_ exacto.

No imprime nombres ni teléfonos.
No persiste información.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv


TIJUANA = ZoneInfo("America/Tijuana")
UTC = ZoneInfo("UTC")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--branch", required=True)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)

    parser.add_argument(
        "--tag",
        action="append",
        required=True,
        dest="tags",
    )

    return parser.parse_args()


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def to_utc_range(
    from_date: date,
    to_date: date,
) -> tuple[str, str]:
    start_local = datetime.combine(
        from_date,
        dt_time.min,
        tzinfo=TIJUANA,
    )

    end_local = (
        datetime.combine(
            to_date + timedelta(days=1),
            dt_time.min,
            tzinfo=TIJUANA,
        )
        - timedelta(microseconds=1)
    )

    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    return (
        start_utc.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
        end_utc.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
    )


def get_ad_tags(
    contact: dict[str, Any],
) -> list[str]:
    tags = contact.get("tags", [])

    if not isinstance(tags, list):
        return []

    return sorted(
        {
            tag.strip()
            for tag in tags
            if isinstance(tag, str)
            and tag.strip().startswith("ad_fb_")
        }
    )


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

    token = os.getenv(
        "IVENTAS_API_TOKEN",
        "",
    ).strip()

    base_url = os.getenv(
        "IVENTAS_API_BASE_URL",
        "https://rest.iventas.mx",
    ).rstrip("/")

    if not token:
        print(
            "ERROR: IVENTAS_API_TOKEN no configurado.",
            file=sys.stderr,
        )
        return 2

    try:
        from_date = parse_date(args.from_date)
        to_date = parse_date(args.to_date)
    except ValueError:
        print(
            "ERROR: fecha inválida.",
            file=sys.stderr,
        )
        return 2

    if to_date < from_date:
        print(
            "ERROR: rango inválido.",
            file=sys.stderr,
        )
        return 2

    from_utc, to_utc = to_utc_range(
        from_date,
        to_date,
    )

    requested_tags = {
        tag.strip()
        for tag in args.tags
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    url = (
        f"{base_url}/v1/integrations/contacts"
    )

    cursor: str | None = None
    pages = 0

    matches: list[
        tuple[dict[str, Any], list[str]]
    ] = []

    print(
        "=== iVentas · inspección por ad tag ==="
    )
    print(f"Branch:  {args.branch}")
    print(
        f"Periodo: {args.from_date} "
        f"-> {args.to_date}"
    )
    print(f"UTC from: {from_utc}")
    print(f"UTC to:   {to_utc}")
    print()

    while True:
        params: dict[str, Any] = {
            "branch": args.branch,
            "from": from_utc,
            "to": to_utc,
            "limit": 100,
        }

        if cursor:
            params["cursor"] = cursor

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

        pages += 1

        print(
            f"Página {pages}: "
            f"HTTP {response.status_code}"
        )

        try:
            payload = response.json()
        except ValueError:
            print(
                "ERROR: respuesta no JSON.",
                file=sys.stderr,
            )
            return 4

        if response.status_code != 200:
            print(
                f"Error iVentas: {payload}"
            )
            return 4

        contacts = payload.get(
            "contacts",
            [],
        )

        if not isinstance(contacts, list):
            print(
                "ERROR: contacts no es lista.",
                file=sys.stderr,
            )
            return 4

        for contact in contacts:
            if not isinstance(contact, dict):
                continue

            tags = get_ad_tags(contact)

            if requested_tags.intersection(tags):
                matches.append(
                    (contact, tags)
                )

        pagination = payload.get(
            "pagination",
            {},
        )

        if not isinstance(pagination, dict):
            break

        if not pagination.get("hasMore"):
            break

        next_cursor = pagination.get(
            "nextCursor"
        )

        if not next_cursor:
            break

        cursor = str(next_cursor)

        time.sleep(1.6)

    print()
    print("=== Resultados ===")
    print(f"Páginas:       {pages}")
    print(f"Coincidencias: {len(matches)}")

    for index, (
        contact,
        tags,
    ) in enumerate(
        matches,
        start=1,
    ):
        print()
        print(f"[{index}]")
        print(
            "contact_id:     "
            f"{contact.get('id', '')}"
        )
        print(
            "createdAt:      "
            f"{contact.get('createdAt', '')}"
        )
        print(
            "firstMessageAt: "
            f"{contact.get('firstMessageAt', '')}"
        )
        print("ad tags:")

        for tag in tags:
            print(f"  {tag}")

    print()
    print(
        "OK: inspección terminada. "
        "No se persistió información."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
