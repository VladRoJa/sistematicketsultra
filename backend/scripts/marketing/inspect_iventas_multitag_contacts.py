"""
Inspección read-only de contactos iVentas con múltiples tags ad_fb_*.

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

    parser.add_argument(
        "--branch",
        required=True,
    )

    parser.add_argument(
        "--from-date",
        required=True,
        help="YYYY-MM-DD local America/Tijuana",
    )

    parser.add_argument(
        "--to-date",
        required=True,
        help="YYYY-MM-DD local America/Tijuana",
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


def extract_ad_tags(
    contact: dict[str, Any],
) -> list[str]:
    tags = contact.get("tags", [])

    if not isinstance(tags, list):
        return []

    result: list[str] = []

    for tag in tags:
        if not isinstance(tag, str):
            continue

        tag = tag.strip()

        if tag.startswith("ad_fb_"):
            result.append(tag)

    return sorted(set(result))


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
            "ERROR: IVENTAS_API_TOKEN "
            "no está configurado.",
            file=sys.stderr,
        )
        return 2

    try:
        from_date = parse_date(args.from_date)
        to_date = parse_date(args.to_date)
    except ValueError:
        print(
            "ERROR: fechas inválidas.",
            file=sys.stderr,
        )
        return 2

    if to_date < from_date:
        print(
            "ERROR: --to-date es anterior a --from-date.",
            file=sys.stderr,
        )
        return 2

    from_utc, to_utc = to_utc_range(
        from_date,
        to_date,
    )

    url = (
        f"{base_url}/v1/integrations/contacts"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    cursor: str | None = None
    contacts: list[dict[str, Any]] = []
    pages = 0

    print(
        "=== iVentas · contactos multi-tag ==="
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
            if isinstance(payload, dict):
                print(
                    "Error iVentas: "
                    f"{payload.get('message', payload)}"
                )
            return 4

        data = payload.get(
            "contacts",
            [],
        )

        if not isinstance(data, list):
            print(
                "ERROR: contacts no es lista.",
                file=sys.stderr,
            )
            return 4

        contacts.extend(
            item
            for item in data
            if isinstance(item, dict)
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

    tagged: list[
        tuple[dict[str, Any], list[str]]
    ] = []

    multi: list[
        tuple[dict[str, Any], list[str]]
    ] = []

    for contact in contacts:
        ad_tags = extract_ad_tags(contact)

        if ad_tags:
            tagged.append(
                (contact, ad_tags)
            )

        if len(ad_tags) > 1:
            multi.append(
                (contact, ad_tags)
            )

    print()
    print("=== Resumen ===")
    print(
        f"Páginas:              {pages}"
    )
    print(
        f"Contactos:             {len(contacts)}"
    )
    print(
        f"Con tag ad_fb_:        {len(tagged)}"
    )
    print(
        f"Con múltiples ad_fb_:  {len(multi)}"
    )

    print()
    print("=== Contactos multi-tag ===")

    if not multi:
        print("(ninguno)")
    else:
        for index, (
            contact,
            ad_tags,
        ) in enumerate(
            multi,
            start=1,
        ):
            print()
            print(f"[{index}]")
            print(
                "contact_id:    "
                f"{contact.get('id', '')}"
            )
            print(
                "createdAt:     "
                f"{contact.get('createdAt', '')}"
            )
            print(
                "firstMessageAt:"
                f" {contact.get('firstMessageAt', '')}"
            )
            print("ad tags:")

            for tag in ad_tags:
                print(f"  {tag}")

    print()
    print(
        "OK: inspección terminada. "
        "No se persistió información."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
