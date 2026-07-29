from __future__ import annotations

import pytest

from app.services.marketing_phone import (
    normalize_member_phone,
    normalize_phone,
)


def test_normalize_phone_accepts_ten_digits():
    assert normalize_phone("(000) 000-0000") == "0000000000"


def test_normalize_phone_removes_mexico_52_prefix():
    assert normalize_phone("+52 000 000 0000") == "0000000000"


def test_normalize_phone_removes_legacy_521_prefix():
    assert normalize_phone("+521 000 000 0000") == "0000000000"


@pytest.mark.parametrize(
    "raw_value",
    [
        None,
        "",
        "000000000",
        "12345678901",
        "+53 000 000 0000",
    ],
)
def test_normalize_phone_rejects_invalid_lengths(raw_value):
    assert normalize_phone(raw_value) is None


def test_normalize_member_phone_falls_back_to_lada_plus_telefono():
    assert (
        normalize_member_phone(
            lada="000",
            telefono="000-0000",
        )
        == "0000000000"
    )


def test_normalize_member_phone_prefers_complete_telefono():
    assert (
        normalize_member_phone(
            lada="999",
            telefono="000 000 0000",
        )
        == "0000000000"
    )
