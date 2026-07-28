from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.warehouse.services.ventas_nuevos_socios_detalle_canonicality_resolver import (
    resolve_ventas_nuevos_socios_detalle_canonicality,
)


BUSINESS_DATE = date(2026, 7, 27)
CAPTURED_AT = datetime(
    2026,
    7,
    27,
    15,
    30,
    tzinfo=timezone.utc,
)


def _resolve(
    *,
    existing=None,
    captured_at=CAPTURED_AT,
    valid=1942,
    rejected=0,
):
    return (
        resolve_ventas_nuevos_socios_detalle_canonicality(
            report_type_key=(
                "ventas_nuevos_socios_detalle"
            ),
            business_date=BUSINESS_DATE,
            date_from=date(2026, 7, 1),
            date_to=BUSINESS_DATE,
            snapshot_kind="month_to_date",
            existing_canonical_snapshot=existing,
            captured_at=captured_at,
            row_count_valid=valid,
            row_count_rejected=rejected,
        )
    )


def test_first_snapshot_is_canonical():
    result = _resolve()

    assert result["is_canonical"] is True
    assert (
        result["replace_existing_canonical"]
        is False
    )


@pytest.mark.parametrize(
    (
        "existing_rejected",
        "existing_valid",
        "existing_captured_at",
        "incoming_rejected",
        "incoming_valid",
        "incoming_captured_at",
    ),
    [
        (
            1,
            2000,
            CAPTURED_AT,
            0,
            1942,
            CAPTURED_AT,
        ),
        (
            0,
            1900,
            CAPTURED_AT,
            0,
            1942,
            CAPTURED_AT,
        ),
        (
            0,
            1942,
            datetime(
                2026,
                7,
                27,
                14,
                0,
                tzinfo=timezone.utc,
            ),
            0,
            1942,
            CAPTURED_AT,
        ),
    ],
)
def test_better_snapshot_replaces_existing(
    existing_rejected,
    existing_valid,
    existing_captured_at,
    incoming_rejected,
    incoming_valid,
    incoming_captured_at,
):
    existing = SimpleNamespace(
        row_count_rejected=existing_rejected,
        row_count_valid=existing_valid,
        captured_at=existing_captured_at,
    )

    result = _resolve(
        existing=existing,
        captured_at=incoming_captured_at,
        valid=incoming_valid,
        rejected=incoming_rejected,
    )

    assert result["is_canonical"] is True
    assert (
        result["replace_existing_canonical"]
        is True
    )


def test_worse_or_older_snapshot_keeps_existing():
    existing = SimpleNamespace(
        row_count_rejected=0,
        row_count_valid=1942,
        captured_at=CAPTURED_AT,
    )

    result = _resolve(
        existing=existing,
        captured_at=datetime(
            2026,
            7,
            27,
            14,
            0,
            tzinfo=timezone.utc,
        ),
        valid=1942,
        rejected=0,
    )

    assert result["is_canonical"] is False
    assert (
        result["replace_existing_canonical"]
        is False
    )
