from __future__ import annotations

import unicodedata
from typing import Any


def normalize_marketing_tariff_key(value: Any) -> str | None:
    """Normaliza la identidad textual de tarifa compartida por Marketing."""
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value)).strip().upper()
    normalized = " ".join(normalized.split())
    return normalized or None
