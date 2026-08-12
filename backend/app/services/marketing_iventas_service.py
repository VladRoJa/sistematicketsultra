"""Reglas de aplicación para la sincronización Marketing + iVentas.

Este módulo coordinará progresivamente:
- periodo comercial America/Tijuana;
- resolución dinámica de sucursales;
- normalización estructurada;
- persistencia raw-first;
- snapshot/canonicalidad.

La comunicación HTTP permanece aislada en
app.integrations.iventas.client.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from typing import Any


TIJUANA_TZ = ZoneInfo("America/Tijuana")

MAX_IVENTAS_PERIOD_DAYS = 31


@dataclass(frozen=True)
class MarketingIventasUtcPeriod:
    """Periodo civil inclusivo convertido al rango UTC de iVentas."""

    date_from: date
    date_to: date

    from_utc: datetime
    to_utc: datetime

    from_iso_z: str
    to_iso_z: str




@dataclass(frozen=True)
class MarketingIventasTimestamp:
    """Timestamp iVentas normalizado a UTC y tiempo civil Tijuana."""

    utc_aware: datetime
    local_tijuana_naive: datetime
    local_tijuana_date: date


def parse_iventas_timestamp(
    value: Any,
) -> MarketingIventasTimestamp | None:
    """Normaliza un timestamp ISO8601 recibido desde iVentas.

    Acepta timestamps con timezone explícito:
    - sufijo Z;
    - offset ISO8601, por ejemplo -07:00 o +00:00.

    None, vacío, formato inválido o timestamp sin timezone
    producen None.

    La representación local se persiste como datetime naive
    deliberadamente: representa la hora civil America/Tijuana.
    """

    raw = str(value or "").strip()

    if not raw:
        return None

    normalized = raw

    if normalized.endswith("Z"):
        normalized = (
            normalized[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )
    except ValueError:
        return None

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        return None

    utc_aware = parsed.astimezone(
        timezone.utc
    )

    local_aware = utc_aware.astimezone(
        TIJUANA_TZ
    )

    local_naive = local_aware.replace(
        tzinfo=None
    )

    return MarketingIventasTimestamp(
        utc_aware=utc_aware,
        local_tijuana_naive=local_naive,
        local_tijuana_date=local_naive.date(),
    )

PHONE_STATUS_MX10_MATCHABLE = "MX10_MATCHABLE"
PHONE_STATUS_NON_MX_OR_UNRESOLVED = "NON_MX_OR_UNRESOLVED"
PHONE_STATUS_MISSING = "MISSING"


@dataclass(frozen=True)
class MarketingIventasPhone:
    """Representación telefónica preservada + matcher MX10."""

    phone_raw: str | None
    phone_digits: str | None
    phone_mx10: str | None
    phone_match_status: str


def normalize_iventas_phone(
    value: Any,
) -> MarketingIventasPhone:
    """Normaliza teléfono sin destruir el valor recibido.

    Reglas MX10 vigentes:
    - 10 dígitos -> mismos 10;
    - 52 + 10 dígitos -> últimos 10;
    - 521 + 10 dígitos -> últimos 10.

    Otros formatos se conservan pero no se fuerzan a MX10.
    """

    if value is None:
        return MarketingIventasPhone(
            phone_raw=None,
            phone_digits=None,
            phone_mx10=None,
            phone_match_status=PHONE_STATUS_MISSING,
        )

    phone_raw = str(value)

    if not phone_raw.strip():
        return MarketingIventasPhone(
            phone_raw=phone_raw,
            phone_digits=None,
            phone_mx10=None,
            phone_match_status=PHONE_STATUS_MISSING,
        )

    digits = "".join(
        char
        for char in phone_raw
        if char.isdigit()
    )

    phone_digits = digits or None

    phone_mx10: str | None = None

    if len(digits) == 10:
        phone_mx10 = digits

    elif (
        len(digits) == 12
        and digits.startswith("52")
    ):
        phone_mx10 = digits[-10:]

    elif (
        len(digits) == 13
        and digits.startswith("521")
    ):
        phone_mx10 = digits[-10:]

    if phone_mx10 is not None:
        status = PHONE_STATUS_MX10_MATCHABLE
    else:
        status = PHONE_STATUS_NON_MX_OR_UNRESOLVED

    return MarketingIventasPhone(
        phone_raw=phone_raw,
        phone_digits=phone_digits,
        phone_mx10=phone_mx10,
        phone_match_status=status,
    )


TAG_KIND_META_AD = "META_AD"
TAG_KIND_OTHER = "OTHER"


@dataclass(frozen=True)
class MarketingIventasNormalizedTag:
    """Observación estructurada de un tag iVentas."""

    tag_raw: str
    tag_kind: str
    meta_ad_id: str | None


@dataclass(frozen=True)
class MarketingIventasNormalizedContact:
    """Contacto iVentas normalizado, aún sin persistencia."""

    sucursal_id: int
    branch_code: str
    contact_id: str
    name: str | None

    phone_raw: str | None
    phone_digits: str | None
    phone_mx10: str | None
    phone_match_status: str

    created_at_utc: datetime
    created_at_local: datetime
    created_date_local: date

    first_message_at_utc: datetime | None
    first_message_at_local: datetime | None
    first_message_date_local: date | None

    channel_id: str | None
    channel_name: str | None
    channel_phone: str | None
    channel_platform: str | None

    agent_json: dict[str, Any] | None

    last_message_status: str | None
    last_outbound_message_at_utc: datetime | None

    row_hash: str

    tags: tuple[MarketingIventasNormalizedTag, ...]


def normalize_iventas_contact(
    *,
    contact: dict[str, Any],
    branch_code: str,
    sucursal_id: int,
) -> MarketingIventasNormalizedContact:
    """Normaliza un contacto iVentas sin tocar DB.

    Reglas importantes:
    - contact.id es identidad obligatoria;
    - createdAt debe ser válido porque es NOT NULL en DB;
    - firstMessageAt y lastOutboundMessageAt son opcionales;
    - channel y agent conservan semántica del proveedor;
    - tags se estructuran aparte;
    - row_hash representa únicamente la fila del contacto,
      no las observaciones de tags.
    """

    if not isinstance(contact, dict):
        raise TypeError(
            "contact debe ser un objeto dict."
        )

    branch_value = str(
        branch_code or ""
    ).strip()

    if not branch_value:
        raise ValueError(
            "branch_code no puede estar vacío."
        )

    if (
        isinstance(sucursal_id, bool)
        or not isinstance(sucursal_id, int)
        or sucursal_id <= 0
    ):
        raise ValueError(
            "sucursal_id debe ser un entero positivo."
        )

    contact_id = str(
        contact.get("id") or ""
    ).strip()

    if not contact_id:
        raise ValueError(
            "El contacto iVentas no tiene id válido."
        )

    phone = normalize_iventas_phone(
        contact.get("phone")
    )

    created = parse_iventas_timestamp(
        contact.get("createdAt")
    )

    if created is None:
        raise ValueError(
            "El contacto iVentas no tiene "
            "createdAt válido con timezone."
        )

    first_message = parse_iventas_timestamp(
        contact.get("firstMessageAt")
    )

    last_outbound = parse_iventas_timestamp(
        contact.get("lastOutboundMessageAt")
    )

    channel = contact.get("channel")

    if channel is not None and not isinstance(
        channel,
        dict,
    ):
        raise ValueError(
            "channel debe ser objeto JSON o null."
        )

    agent = contact.get("agent")

    if agent is not None and not isinstance(
        agent,
        dict,
    ):
        raise ValueError(
            "agent debe ser objeto JSON o null."
        )

    tags = _normalize_iventas_tags(
        contact.get("tags")
    )

    name = _optional_text(
        contact.get("name")
    )

    channel_id = _dict_optional_text(
        channel,
        "id",
    )

    channel_name = _dict_optional_text(
        channel,
        "name",
    )

    channel_phone = _dict_optional_text(
        channel,
        "phone",
    )

    channel_platform = _dict_optional_text(
        channel,
        "platform",
    )

    agent_json = (
        deepcopy(agent)
        if agent is not None
        else None
    )

    last_message_status = _optional_text(
        contact.get("lastMessageStatus")
    )

    first_message_at_utc = (
        first_message.utc_aware
        if first_message is not None
        else None
    )

    first_message_at_local = (
        first_message.local_tijuana_naive
        if first_message is not None
        else None
    )

    first_message_date_local = (
        first_message.local_tijuana_date
        if first_message is not None
        else None
    )

    last_outbound_message_at_utc = (
        last_outbound.utc_aware
        if last_outbound is not None
        else None
    )

    hash_payload = {
        "sucursal_id": sucursal_id,
        "branch_code": branch_value,
        "contact_id": contact_id,
        "name": name,
        "phone_raw": phone.phone_raw,
        "phone_digits": phone.phone_digits,
        "phone_mx10": phone.phone_mx10,
        "phone_match_status": (
            phone.phone_match_status
        ),
        "created_at_utc": (
            created.utc_aware.isoformat()
        ),
        "created_at_local": (
            created.local_tijuana_naive.isoformat()
        ),
        "created_date_local": (
            created.local_tijuana_date.isoformat()
        ),
        "first_message_at_utc": (
            first_message_at_utc.isoformat()
            if first_message_at_utc is not None
            else None
        ),
        "first_message_at_local": (
            first_message_at_local.isoformat()
            if first_message_at_local is not None
            else None
        ),
        "first_message_date_local": (
            first_message_date_local.isoformat()
            if first_message_date_local is not None
            else None
        ),
        "channel_id": channel_id,
        "channel_name": channel_name,
        "channel_phone": channel_phone,
        "channel_platform": channel_platform,
        "agent_json": agent_json,
        "last_message_status": (
            last_message_status
        ),
        "last_outbound_message_at_utc": (
            last_outbound_message_at_utc.isoformat()
            if last_outbound_message_at_utc
            is not None
            else None
        ),
    }

    row_hash = _build_iventas_contact_row_hash(
        hash_payload
    )

    return MarketingIventasNormalizedContact(
        sucursal_id=sucursal_id,
        branch_code=branch_value,
        contact_id=contact_id,
        name=name,
        phone_raw=phone.phone_raw,
        phone_digits=phone.phone_digits,
        phone_mx10=phone.phone_mx10,
        phone_match_status=(
            phone.phone_match_status
        ),
        created_at_utc=created.utc_aware,
        created_at_local=(
            created.local_tijuana_naive
        ),
        created_date_local=(
            created.local_tijuana_date
        ),
        first_message_at_utc=(
            first_message_at_utc
        ),
        first_message_at_local=(
            first_message_at_local
        ),
        first_message_date_local=(
            first_message_date_local
        ),
        channel_id=channel_id,
        channel_name=channel_name,
        channel_phone=channel_phone,
        channel_platform=channel_platform,
        agent_json=agent_json,
        last_message_status=(
            last_message_status
        ),
        last_outbound_message_at_utc=(
            last_outbound_message_at_utc
        ),
        row_hash=row_hash,
        tags=tags,
    )


def _normalize_iventas_tags(
    raw_tags: Any,
) -> tuple[MarketingIventasNormalizedTag, ...]:
    """Clasifica tags conservando cada valor textual."""

    if raw_tags is None:
        return ()

    if not isinstance(raw_tags, list):
        raise ValueError(
            "tags debe ser lista o null."
        )

    result: list[
        MarketingIventasNormalizedTag
    ] = []

    seen: set[str] = set()

    for raw_tag in raw_tags:
        if not isinstance(raw_tag, str):
            raise ValueError(
                "Cada tag iVentas debe ser string."
            )

        if not raw_tag.strip():
            raise ValueError(
                "Un tag iVentas no puede estar vacío."
            )

        # La identidad contractual del tag conserva
        # exactamente el string recibido.
        if raw_tag in seen:
            continue

        seen.add(raw_tag)

        prefix = "ad_fb_"

        if (
            raw_tag.startswith(prefix)
            and raw_tag[len(prefix):].isdigit()
            and raw_tag[len(prefix):]
        ):
            tag_kind = TAG_KIND_META_AD
            meta_ad_id = raw_tag[len(prefix):]
        else:
            tag_kind = TAG_KIND_OTHER
            meta_ad_id = None

        result.append(
            MarketingIventasNormalizedTag(
                tag_raw=raw_tag,
                tag_kind=tag_kind,
                meta_ad_id=meta_ad_id,
            )
        )

    return tuple(result)


def _optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    return str(value)


def _dict_optional_text(
    value: dict[str, Any] | None,
    key: str,
) -> str | None:
    if value is None:
        return None

    return _optional_text(
        value.get(key)
    )


def _build_iventas_contact_row_hash(
    payload: dict[str, Any],
) -> str:
    """SHA-256 de la fila estructurada canónica del contacto."""

    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()

def build_iventas_utc_period(
    *,
    date_from: date,
    date_to: date,
) -> MarketingIventasUtcPeriod:
    """Convierte fechas civiles Tijuana a rango UTC inclusivo.

    iVentas admite como máximo 31 días civiles por consulta.

    El instante inicial es 00:00:00.000 local.
    El instante final es 23:59:59.999 local.
    """

    if date_to < date_from:
        raise ValueError(
            "date_to no puede ser anterior a date_from."
        )

    civil_days = (
        date_to - date_from
    ).days + 1

    if civil_days > MAX_IVENTAS_PERIOD_DAYS:
        raise ValueError(
            "iVentas permite como máximo "
            "31 días civiles por consulta."
        )

    local_start = datetime.combine(
        date_from,
        time(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ),
        tzinfo=TIJUANA_TZ,
    )

    local_end = datetime.combine(
        date_to,
        time(
            hour=23,
            minute=59,
            second=59,
            microsecond=999000,
        ),
        tzinfo=TIJUANA_TZ,
    )

    from_utc = local_start.astimezone(
        timezone.utc
    )

    to_utc = local_end.astimezone(
        timezone.utc
    )

    return MarketingIventasUtcPeriod(
        date_from=date_from,
        date_to=date_to,
        from_utc=from_utc,
        to_utc=to_utc,
        from_iso_z=_to_iventas_iso_z(
            from_utc
        ),
        to_iso_z=_to_iventas_iso_z(
            to_utc
        ),
    )


def _to_iventas_iso_z(
    value: datetime,
) -> str:
    """Serializa UTC con milisegundos exactos y sufijo Z."""

    if value.tzinfo is None:
        raise ValueError(
            "El datetime debe incluir timezone."
        )

    utc_value = value.astimezone(
        timezone.utc
    )

    return (
        utc_value.isoformat(
            timespec="milliseconds"
        )
        .replace("+00:00", "Z")
    )
