"""Focused safety checks for one-off Campaign #41 recovery ordering."""
from types import SimpleNamespace as NS

import pytest

from scripts.resume_campaign41_ready import (
    RecoveryBlocked,
    _check_original_order,
)


def _row(row_id, status, *, provider_id=None, submitted=False, attempted=False):
    return NS(
        id=row_id,
        status=status,
        provider_campaign_id=provider_id,
        submitted_at=object() if submitted else None,
        submit_started_at=object() if attempted else None,
    )


def _original():
    return [
        _row(253, "SUBMITTED", provider_id="provider-a", submitted=True, attempted=True),
        _row(254, "SUBMITTED", provider_id="provider-b", submitted=True, attempted=True),
        _row(255, "PROVIDER_ERROR", attempted=True),
        _row(256, "READY"),
        _row(257, "READY"),
    ]


def test_only_returns_ready_suffix_never_repeats_accepted_or_failed():
    assert [r.id for r in _check_original_order(_original(), 255)] == [256, 257]


@pytest.mark.parametrize("change", [
    lambda x: setattr(x[0], "status", "READY"),
    lambda x: setattr(x[0], "provider_campaign_id", None),
    lambda x: setattr(x[2], "status", "SUBMITTED"),
    lambda x: setattr(x[3], "status", "SUBMITTED"),
    lambda x: setattr(x[3], "submit_started_at", object()),
    lambda x: setattr(x[4], "provider_campaign_id", "external-duplicate"),
])
def test_fails_closed_on_history_or_pending_drift(change):
    rows = _original()
    change(rows)
    with pytest.raises(RecoveryBlocked):
        _check_original_order(rows, 255)


def test_requires_accepted_prefix_and_pending_suffix():
    with pytest.raises(RecoveryBlocked):
        _check_original_order(_original()[2:], 255)
    with pytest.raises(RecoveryBlocked):
        _check_original_order(_original()[:3], 255)


def test_requires_unique_child_ids():
    rows = _original()
    rows[4].id = 256
    with pytest.raises(RecoveryBlocked):
        _check_original_order(rows, 255)
