from __future__ import annotations

import re
from typing import Any


def normalize_phone(raw_value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(raw_value or ""))

    if len(digits) == 10:
        return digits

    if len(digits) == 12 and digits.startswith("52"):
        return digits[-10:]

    if len(digits) == 13 and digits.startswith("521"):
        return digits[-10:]

    return None


def normalize_member_phone(
    *,
    lada: Any,
    telefono: Any,
) -> str | None:
    direct_phone = normalize_phone(telefono)
    if direct_phone is not None:
        return direct_phone

    return normalize_phone(f"{lada or ''}{telefono or ''}")


def format_mexico_international_phone(raw_value: Any) -> str | None:
    """Project canonical MX10 identity to provider transport digits.

    This is deliberately a formatter, not another normalizer: validity and
    canonical identity continue to come exclusively from normalize_phone().
    """

    phone_mx10 = normalize_phone(raw_value)
    if phone_mx10 is None:
        return None
    return f"52{phone_mx10}"


def mask_phone(raw_value: Any) -> str:
    digits = re.sub(r"\D", "", str(raw_value or ""))
    if not digits:
        return "Sin teléfono"
    return f"*** *** {digits[-4:]}"
