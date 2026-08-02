from __future__ import annotations

import unicodedata


def normalize_identity_name(value: object) -> str | None:
    collapsed = " ".join(str(value or "").split())
    if not collapsed:
        return None

    decomposed = unicodedata.normalize("NFKD", collapsed.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in without_marks
    )
    normalized = " ".join(without_punctuation.split())
    return normalized or None
