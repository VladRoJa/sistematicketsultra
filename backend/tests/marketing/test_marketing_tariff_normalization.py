from __future__ import annotations

import pytest

from app.services.marketing_reactivation_service import (
    normalize_reactivation_tariff_key,
)
from app.services.marketing_tariff_normalization import (
    normalize_marketing_tariff_key,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Mensualidad", "MENSUALIDAD"),
        ("  plan   familiar\t $599  ", "PLAN FAMILIAR $599"),
        ("ＭＥＭＢＲＥＳＩＡ　ＬＭ", "MEMBRESIA LM"),
        (None, None),
        (" \t\n ", None),
    ],
)
def test_shared_tariff_normalizer_matches_legacy_api(value, expected):
    assert normalize_marketing_tariff_key(value) == expected
    assert normalize_reactivation_tariff_key(value) == expected
    assert normalize_reactivation_tariff_key(value) == normalize_marketing_tariff_key(value)
