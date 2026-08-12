"""
Inspección read-only de la API de contactos de iVentas.

No persiste información.
No imprime el Bearer token.
No imprime nombres ni teléfonos completos.

Ejemplo:
    python scripts/marketing/inspect_iventas_contacts.py \
        --branch papalote \
        --from-date 2026-08-01 \
        --to-date 2026-08-02
"""

from __future__ import annotations

import argparse
import os
import sys
import time as time_module
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests


TIJUANA_TZ = ZoneInfo("America/Tijuana")

DEFAULT_BASE_URL = "https://rest.iventas.mx"

ALLOWED_BRANCHES = {
    "tlalnepantla",
    "sendero-chihuahua",
    "villa-verde",
    "azahares",
    "santa-fe",
    "villas-del-rey",
    "tecnologico",
    "carrousel",
    "ixtapaluca",
    "san-luis-rio-colorado",
    "saltillo-sur",
    "insurgentes",
    "san-isidro",
    "loma-bonita",
    "paseo-2000",
    "santa-catarina",
    "mision",
    "paseo-la-paz",
    "sendero-culiacan",
    "independencia",
    "pabellon-rosarito",
    "sendero-mexicali",
    "papalote",
    "villalta",
    "serrania",
    "metepec",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Consulta una sola página de contactos iVentas "
            "sin persistir datos."
        )
    )

    parser.add_argument(
        "--branch",
        required=True,
        choices=sorted(ALLOWED_BRANCHES),
        help="Código oficial de sucursal iVentas.",
    )

    parser.add_argument(
        "--from-date",
        required=True,
        type=date.fromisoformat,
        help="Fecha inicial civil America/Tijuana: YYYY-MM-DD.",
    )

    parser.add_argument(
        "--to-date",
        required=True,
        type=date.fromisoformat,
        help="Fecha final civil America/Tijuana: YYYY-MM-DD.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Contactos por página. Máximo 100.",
    )

    parser.add_argument(
        "--all-pages",
        action="store_true",
        help=(
            "Recorre toda la paginación de la sucursal. "
            "Respeta un máximo interno de 40 requests/minuto."
        ),
    )

    return parser.parse_args()


def validate_period(
    from_date: date,
    to_date: date,
    limit: int,
) -> None:
    if to_date < from_date:
        raise ValueError(
            "--to-date no puede ser anterior a --from-date."
        )

    # 1-jul -> 31-jul = diferencia de 30 días:
    # son 31 días civiles y sigue siendo válido.
    if (to_date - from_date).days > 30:
        raise ValueError(
            "iVentas permite como máximo 31 días civiles por consulta."
        )

    if not 1 <= limit <= 100:
        raise ValueError("--limit debe estar entre 1 y 100.")


def local_period_to_utc(
    from_date: date,
    to_date: date,
) -> tuple[datetime, datetime]:
    local_start = datetime.combine(
        from_date,
        time.min,
        tzinfo=TIJUANA_TZ,
    )

    # Construimos el instante anterior al inicio del día siguiente.
    local_end = (
        datetime.combine(
            to_date + timedelta(days=1),
            time.min,
            tzinfo=TIJUANA_TZ,
        )
        - timedelta(milliseconds=1)
    )

    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )


def to_iso_z(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)

    return (
        utc_value.isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def normalize_phone(value: Any) -> str | None:
    digits = "".join(
        char
        for char in str(value or "")
        if char.isdigit()
    )

    if len(digits) == 10:
        return digits

    if (
        len(digits) == 12
        and digits.startswith("52")
    ):
        return digits[-10:]

    if (
        len(digits) == 13
        and digits.startswith("521")
    ):
        return digits[-10:]

    return None


def phone_shape(value: Any) -> str:
    digits = "".join(
        char
        for char in str(value or "")
        if char.isdigit()
    )

    if not digits:
        return "SIN_TELEFONO"

    if len(digits) <= 3:
        prefix = digits
    else:
        prefix = digits[:3]

    return f"{len(digits)}_DIGITOS_PREFIJO_{prefix}"


def mask_phone(value: Any) -> str:
    digits = "".join(
        char for char in str(value or "")
        if char.isdigit()
    )

    if not digits:
        return "(sin teléfono)"

    if len(digits) <= 4:
        return "*" * len(digits)

    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def extract_tag_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    labels: list[str] = []

    for item in value:
        if isinstance(item, str):
            label = item.strip()

            if label:
                labels.append(label)

            continue

        if not isinstance(item, dict):
            continue

        candidate = (
            item.get("name")
            or item.get("label")
            or item.get("title")
            or item.get("value")
        )

        label = str(candidate or "").strip()

        if label:
            labels.append(label)

    return labels


def parse_created_at(value: Any) -> datetime | None:
    raw = str(value or "").strip()

    if not raw:
        return None

    try:
        return datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def safe_error_code(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "(respuesta no JSON)"

    if isinstance(payload, dict):
        return str(payload.get("error") or "(sin código)")

    return "(sin código)"


def inspect_contacts(
    *,
    branch: str,
    from_date: date,
    to_date: date,
    limit: int,
    all_pages: bool,
) -> int:
    token = os.getenv("IVENTAS_API_TOKEN", "").strip()

    if not token:
        print(
            "ERROR: IVENTAS_API_TOKEN no está configurado.",
            file=sys.stderr,
        )
        return 2

    base_url = (
        os.getenv(
            "IVENTAS_API_BASE_URL",
            DEFAULT_BASE_URL,
        )
        .strip()
        .rstrip("/")
    )

    from_utc, to_utc = local_period_to_utc(
        from_date,
        to_date,
    )

    url = f"{base_url}/v1/integrations/contacts"

    base_params = {
        "branch": branch,
        "from": to_iso_z(from_utc),
        "to": to_iso_z(to_utc),
        "limit": limit,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    print("=== iVentas read-only inspection ===")
    print(f"Branch:           {branch}")
    print(
        "Periodo local:    "
        f"{from_date.isoformat()} -> {to_date.isoformat()} "
        "(America/Tijuana)"
    )
    print(f"From UTC:         {base_params['from']}")
    print(f"To UTC:           {base_params['to']}")
    print(f"Limit:            {limit}")
    print(
        "Paginación:       "
        f"{'completa' if all_pages else 'solo primera página'}"
    )
    print()

    cursor: str | None = None
    page_number = 0

    contacts_total = 0
    phones_present = 0
    valid_normalizable_phone = 0
    invalid_phone = 0

    platforms: Counter[str] = Counter()
    channel_names: Counter[str] = Counter()
    channel_ids: Counter[str] = Counter()
    tag_labels: Counter[str] = Counter()

    contact_keys: set[str] = set()
    channel_keys: set[str] = set()
    tag_keys: set[str] = set()

    contacts_with_tags = 0
    contacts_without_tags = 0
    first_message_present = 0
    first_message_missing = 0
    first_message_same_as_created = 0
    first_message_different_from_created = 0
    first_message_inside_period = 0
    first_message_outside_period = 0
    first_message_deltas_seconds: list[float] = []

    meta_ad_contacts = 0
    meta_ad_contacts_with_valid_phone = 0
    meta_ad_contacts_multiple_ads = 0
    meta_ad_first_message_present = 0
    meta_ad_first_message_missing = 0
    meta_ad_first_message_inside_period = 0
    meta_ad_first_message_outside_period = 0
    meta_ad_first_message_same_created = 0
    meta_ad_first_message_different_created = 0
    meta_ad_first_message_deltas_seconds: list[float] = []

    meta_ad_ids: Counter[str] = Counter()
    meta_ad_phones: Counter[str] = Counter()

    phone_lengths: Counter[int] = Counter()
    phone_shapes: Counter[str] = Counter()
    normalized_phones: Counter[str] = Counter()
    contact_ids: Counter[str] = Counter()

    created_values: list[datetime] = []
    samples: list[str] = []

    branch_response_code = ""
    branch_response_label = ""

    while True:
        page_number += 1

        params = dict(base_params)

        if cursor:
            params["cursor"] = cursor

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=(10, 30),
            )
        except requests.Timeout:
            print(
                f"ERROR: timeout en página {page_number}.",
                file=sys.stderr,
            )
            return 3
        except requests.RequestException as exc:
            print(
                "ERROR HTTP "
                f"en página {page_number}: "
                f"{exc.__class__.__name__}",
                file=sys.stderr,
            )
            return 3

        print(
            f"Página {page_number}: "
            f"HTTP {response.status_code}"
        )

        if response.status_code != 200:
            print(
                "Error iVentas:    "
                f"{safe_error_code(response)}"
            )
            return 4

        try:
            payload = response.json()
        except ValueError:
            print(
                "ERROR: iVentas respondió 200 pero no JSON.",
                file=sys.stderr,
            )
            return 5

        if not isinstance(payload, dict):
            print(
                "ERROR: payload raíz inesperado.",
                file=sys.stderr,
            )
            return 5

        contacts = payload.get("contacts")
        pagination = payload.get("pagination")
        branch_payload = payload.get("branch")

        if not isinstance(contacts, list):
            print(
                "ERROR: 'contacts' no es una lista.",
                file=sys.stderr,
            )
            return 5

        if not isinstance(pagination, dict):
            print(
                "ERROR: falta objeto 'pagination'.",
                file=sys.stderr,
            )
            return 5

        if isinstance(branch_payload, dict):
            branch_response_code = str(
                branch_payload.get("code") or ""
            )
            branch_response_label = str(
                branch_payload.get("label") or ""
            )

        print(
            f"  contactos={len(contacts)} "
            f"hasMore={bool(pagination.get('hasMore'))} "
            "nextCursor="
            f"{'sí' if pagination.get('nextCursor') else 'no'}"
        )

        contacts_total += len(contacts)

        for contact in contacts:
            if not isinstance(contact, dict):
                continue

            contact_keys.update(
                str(key) for key in contact.keys()
            )

            contact_id = str(
                contact.get("id") or ""
            ).strip()

            if contact_id:
                contact_ids[contact_id] += 1

            phone = contact.get("phone")

            digits = "".join(
                char
                for char in str(phone or "")
                if char.isdigit()
            )

            phone_shapes[phone_shape(phone)] += 1

            if digits:
                phones_present += 1
                phone_lengths[len(digits)] += 1

            normalized_phone = normalize_phone(phone)

            if normalized_phone:
                valid_normalizable_phone += 1
                normalized_phones[normalized_phone] += 1
            else:
                invalid_phone += 1

            created_at = parse_created_at(
                contact.get("createdAt")
            )

            if created_at is not None:
                created_values.append(created_at)

            first_message_at = parse_created_at(
                contact.get("firstMessageAt")
            )

            if first_message_at is None:
                first_message_missing += 1
            else:
                first_message_present += 1

                first_message_utc = first_message_at.astimezone(
                    timezone.utc
                )

                if from_utc <= first_message_utc <= to_utc:
                    first_message_inside_period += 1
                else:
                    first_message_outside_period += 1

                if created_at is not None:
                    delta_seconds = (
                        first_message_at - created_at
                    ).total_seconds()

                    first_message_deltas_seconds.append(
                        delta_seconds
                    )

                    if abs(delta_seconds) < 1:
                        first_message_same_as_created += 1
                    else:
                        first_message_different_from_created += 1

            raw_tags = contact.get("tags")
            labels = extract_tag_labels(raw_tags)

            if labels:
                contacts_with_tags += 1

                for label in labels:
                    tag_labels[label] += 1
            else:
                contacts_without_tags += 1

            meta_tags = sorted(
                {
                    label
                    for label in labels
                    if label.lower().startswith("ad_fb_")
                }
            )

            if meta_tags:
                meta_ad_contacts += 1

                for meta_tag in meta_tags:
                    meta_ad_ids[meta_tag] += 1

                if len(meta_tags) > 1:
                    meta_ad_contacts_multiple_ads += 1

                if normalized_phone:
                    meta_ad_contacts_with_valid_phone += 1
                    meta_ad_phones[normalized_phone] += 1

                if first_message_at is None:
                    meta_ad_first_message_missing += 1
                else:
                    meta_ad_first_message_present += 1

                    first_message_utc = (
                        first_message_at.astimezone(
                            timezone.utc
                        )
                    )

                    if from_utc <= first_message_utc <= to_utc:
                        meta_ad_first_message_inside_period += 1
                    else:
                        meta_ad_first_message_outside_period += 1

                    if created_at is not None:
                        meta_delta = (
                            first_message_at - created_at
                        ).total_seconds()

                        meta_ad_first_message_deltas_seconds.append(
                            meta_delta
                        )

                        if abs(meta_delta) < 1:
                            meta_ad_first_message_same_created += 1
                        else:
                            meta_ad_first_message_different_created += 1

            if isinstance(raw_tags, list):
                for tag in raw_tags:
                    if isinstance(tag, dict):
                        tag_keys.update(
                            str(key)
                            for key in tag.keys()
                        )

            channel = contact.get("channel")

            if isinstance(channel, dict):
                channel_keys.update(
                    str(key) for key in channel.keys()
                )

                platform = str(
                    channel.get("platform")
                    or "SIN_PLATAFORMA"
                ).strip()

                channel_name = str(
                    channel.get("name")
                    or "SIN_NOMBRE"
                ).strip()

                channel_id = str(
                    channel.get("id")
                    or "SIN_ID"
                ).strip()

                channel_names[
                    channel_name or "SIN_NOMBRE"
                ] += 1

                channel_ids[
                    channel_id or "SIN_ID"
                ] += 1
            else:
                platform = "SIN_CANAL"
                channel_names["SIN_CANAL"] += 1
                channel_ids["SIN_CANAL"] += 1

            platforms[
                platform or "SIN_PLATAFORMA"
            ] += 1

            if len(samples) < 5:
                local_created = (
                    created_at
                    .astimezone(TIJUANA_TZ)
                    .isoformat(timespec="seconds")
                    if created_at is not None
                    else "(fecha inválida)"
                )

                samples.append(
                    f"{mask_phone(phone)} | "
                    f"{platform} | "
                    f"{local_created}"
                )

        has_more = bool(
            pagination.get("hasMore")
        )
        next_cursor = pagination.get(
            "nextCursor"
        )

        if not all_pages or not has_more:
            break

        if not next_cursor:
            print(
                "ERROR: hasMore=true pero "
                "nextCursor está vacío.",
                file=sys.stderr,
            )
            return 5

        cursor = str(next_cursor)

        # 40 req/min => mínimo teórico 1.5 s.
        # Dejamos margen adicional.
        time_module.sleep(1.6)

    duplicate_ids = {
        contact_id: count
        for contact_id, count in contact_ids.items()
        if count > 1
    }

    repeated_phones = {
        phone: count
        for phone, count in normalized_phones.items()
        if count > 1
    }

    contacts_on_repeated_phones = sum(
        repeated_phones.values()
    )

    print()
    print("=== Resumen ===")
    print(
        "Branch response:   "
        f"{branch_response_code or '(sin code)'} / "
        f"{branch_response_label or '(sin label)'}"
    )
    print(f"Páginas:           {page_number}")
    print(f"Contactos:         {contacts_total}")
    print(
        "IDs únicos:        "
        f"{len(contact_ids)}"
    )
    print(
        "IDs duplicados:    "
        f"{len(duplicate_ids)}"
    )
    print(
        "Con teléfono:      "
        f"{phones_present}/{contacts_total}"
    )
    print(
        "Normalizables:     "
        f"{valid_normalizable_phone}/{contacts_total}"
    )
    print(
        "Teléfono inválido: "
        f"{invalid_phone}/{contacts_total}"
    )
    print(
        "Teléfonos únicos:  "
        f"{len(normalized_phones)}"
    )
    print(
        "Teléfonos repetidos:"
        f" {len(repeated_phones)}"
    )
    print(
        "Contactos en tel. "
        "repetidos: "
        f"{contacts_on_repeated_phones}"
    )

    print()
    print("Longitudes de teléfono:")

    if phone_lengths:
        for length, count in sorted(
            phone_lengths.items()
        ):
            print(f"  {length} dígitos: {count}")
    else:
        print("  (ninguna)")

    print()
    print("Formas de teléfono:")

    for shape, count in sorted(
        phone_shapes.items()
    ):
        print(f"  {shape}: {count}")

    if created_values:
        first = min(
            created_values
        ).astimezone(TIJUANA_TZ)

        last = max(
            created_values
        ).astimezone(TIJUANA_TZ)

        print()
        print(
            "Primer contacto:  "
            f"{first.isoformat(timespec='seconds')}"
        )
        print(
            "Último contacto:  "
            f"{last.isoformat(timespec='seconds')}"
        )

    print()
    print("Schema observado:")
    print(
        "  contact: "
        + ", ".join(sorted(contact_keys))
    )
    print(
        "  channel: "
        + ", ".join(sorted(channel_keys))
    )
    print(
        "  tag: "
        + (
            ", ".join(sorted(tag_keys))
            if tag_keys
            else "(sin objetos tag observados)"
        )
    )

    print()
    print("Tags:")
    print(
        "  contactos con tags: "
        f"{contacts_with_tags}"
    )
    print(
        "  contactos sin tags: "
        f"{contacts_without_tags}"
    )
    print(
        "  tags distintos: "
        f"{len(tag_labels)}"
    )

    if tag_labels:
        print("  principales tags:")

        for label, count in tag_labels.most_common(10):
            print(f"    {label}: {count}")
    else:
        print("  (ninguno)")

    print()
    print("Meta Ads · tags ad_fb_*:")
    print(
        "  contactos Meta: "
        f"{meta_ad_contacts}"
    )
    print(
        "  contactos no Meta: "
        f"{contacts_total - meta_ad_contacts}"
    )
    print(
        "  Meta con teléfono normalizable: "
        f"{meta_ad_contacts_with_valid_phone}"
    )
    print(
        "  teléfonos Meta únicos: "
        f"{len(meta_ad_phones)}"
    )
    print(
        "  contactos con múltiples anuncios: "
        f"{meta_ad_contacts_multiple_ads}"
    )
    print(
        "  anuncios Meta distintos: "
        f"{len(meta_ad_ids)}"
    )
    print(
        "  firstMessageAt presente: "
        f"{meta_ad_first_message_present}"
    )
    print(
        "  firstMessageAt ausente: "
        f"{meta_ad_first_message_missing}"
    )
    print(
        "  firstMessageAt dentro del periodo: "
        f"{meta_ad_first_message_inside_period}"
    )
    print(
        "  firstMessageAt fuera del periodo: "
        f"{meta_ad_first_message_outside_period}"
    )
    print(
        "  firstMessageAt = createdAt: "
        f"{meta_ad_first_message_same_created}"
    )
    print(
        "  firstMessageAt != createdAt: "
        f"{meta_ad_first_message_different_created}"
    )

    if meta_ad_first_message_deltas_seconds:
        print(
            "  delta Meta mínimo segundos: "
            f"{min(meta_ad_first_message_deltas_seconds):.0f}"
        )
        print(
            "  delta Meta máximo segundos: "
            f"{max(meta_ad_first_message_deltas_seconds):.0f}"
        )

    if meta_ad_ids:
        print("  anuncios con más contactos:")

        for ad_id, count in meta_ad_ids.most_common(10):
            print(f"    {ad_id}: {count}")

    print()
    print("firstMessageAt:")
    print(
        "  presente: "
        f"{first_message_present}"
    )
    print(
        "  ausente: "
        f"{first_message_missing}"
    )
    print(
        "  igual a createdAt: "
        f"{first_message_same_as_created}"
    )
    print(
        "  diferente de createdAt: "
        f"{first_message_different_from_created}"
    )
    print(
        "  dentro del periodo solicitado: "
        f"{first_message_inside_period}"
    )
    print(
        "  fuera del periodo solicitado: "
        f"{first_message_outside_period}"
    )

    if first_message_deltas_seconds:
        print(
            "  delta mínimo segundos: "
            f"{min(first_message_deltas_seconds):.0f}"
        )
        print(
            "  delta máximo segundos: "
            f"{max(first_message_deltas_seconds):.0f}"
        )

    print()
    print("Plataformas:")

    if platforms:
        for platform, count in sorted(
            platforms.items()
        ):
            print(f"  {platform}: {count}")
    else:
        print("  (ninguna)")

    print()
    print(
        "Channels distintos por ID: "
        f"{len(channel_ids)}"
    )

    print("Channel names:")

    for channel_name, count in sorted(
        channel_names.items()
    ):
        print(f"  {channel_name}: {count}")

    print()
    print("Muestra anonimizada:")

    if samples:
        for sample in samples:
            print(f"  {sample}")
    else:
        print("  (sin contactos)")

    print()
    print(
        "OK: consulta terminada. "
        "No se persistió información."
    )

    return 0


def main() -> int:
    args = parse_args()

    try:
        validate_period(
            args.from_date,
            args.to_date,
            args.limit,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return inspect_contacts(
        branch=args.branch,
        from_date=args.from_date,
        to_date=args.to_date,
        limit=args.limit,
        all_pages=args.all_pages,
    )


if __name__ == "__main__":
    raise SystemExit(main())
