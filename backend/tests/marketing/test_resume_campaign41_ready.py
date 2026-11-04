"""Focused safety checks for one-off Campaign #41 recovery ordering."""
from types import SimpleNamespace as NS
from unittest.mock import Mock

from app.services import marketing_campaign_v2_governed_recovery_service as governed_recovery
from datetime import datetime, timedelta, timezone

import pytest

from scripts.resume_campaign41_ready import (
    RecoveryBlocked,
    _check_original_order,
    _validate_started_dispatch_window,
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


def _time_rows():
    # First provider claim is within the approval TTL, but the failed child
    # legitimately starts after that TTL while the accepted prefix completes.
    start = datetime(2026, 11, 3, 23, 30, tzinfo=timezone.utc)
    rows = _original()
    rows[0].submit_started_at = start + timedelta(minutes=2)
    rows[0].submitted_at = start + timedelta(minutes=3)
    rows[1].submit_started_at = start + timedelta(minutes=14)
    rows[1].submitted_at = start + timedelta(minutes=15)
    rows[2].submit_started_at = start + timedelta(minutes=16)
    return start, rows


def test_failed_child_may_start_after_initial_approval_expiry():
    start, rows = _time_rows()
    _check_original_order(rows, 255)
    _validate_started_dispatch_window(
        ready_rows=rows, failed_id=255,
        confirmed_at=start, expires_at=start + timedelta(minutes=10),
    )


def test_first_provider_claim_must_precede_approval_expiry():
    start, rows = _time_rows()
    with pytest.raises(RecoveryBlocked, match="primer envío"):
        _validate_started_dispatch_window(
            ready_rows=rows, failed_id=255,
            confirmed_at=start, expires_at=start + timedelta(minutes=1),
        )


def test_first_claim_must_follow_independent_confirmation():
    start, rows = _time_rows()
    with pytest.raises(RecoveryBlocked, match="primer envío"):
        _validate_started_dispatch_window(
            ready_rows=rows, failed_id=255,
            confirmed_at=start + timedelta(minutes=3),
            expires_at=start + timedelta(minutes=10),
        )


def test_failed_claim_cannot_precede_last_accepted_completion():
    start, rows = _time_rows()
    rows[2].submit_started_at = start + timedelta(minutes=14)
    with pytest.raises(RecoveryBlocked, match="no sigue al prefijo"):
        _validate_started_dispatch_window(
            ready_rows=rows, failed_id=255,
            confirmed_at=start, expires_at=start + timedelta(minutes=10),
        )


def test_accepted_claims_must_be_sequential_even_after_expiry():
    start, rows = _time_rows()
    rows[1].submit_started_at = start + timedelta(minutes=2)
    with pytest.raises(RecoveryBlocked, match="orden temporal"):
        _validate_started_dispatch_window(
            ready_rows=rows, failed_id=255,
            confirmed_at=start, expires_at=start + timedelta(minutes=10),
        )



def _governed_row(row_id, status, *, provider_id=None, actor=7):
    return NS(
        id=row_id, status=status, provider_campaign_id=provider_id,
        error_code="TEMPLATE_NOT_FOUND" if row_id == 255 else None,
        support_ref="bc-mw1c1why-phq041" if row_id == 255 else None,
        submitted_at=object() if status == "SUBMITTED" else None,
        submit_started_at=object() if status == "SUBMITTED" else None,
        submitted_by_user_id=actor if status == "SUBMITTED" else None,
    )


def test_governed_skip_preserves_original_provider_prefix_and_ready_suffix():
    rows = [
        _governed_row(253, "SUBMITTED", provider_id="old-253"),
        _governed_row(254, "SUBMITTED", provider_id="old-254"),
        _governed_row(255, "PROVIDER_ERROR"),
        _governed_row(256, "READY"),
        _governed_row(257, "READY"),
    ]
    governed_recovery.verify_suffix(
        rows=rows, accepted_original=((253, "old-253"), (254, "old-254")),
        ready_ids=(256, 257), completed=(),
        next_id=256, actor_user_id=7,
    )
    rows[3] = _governed_row(256, "SUBMITTED", provider_id="new-256")
    governed_recovery.verify_suffix(
        rows=rows, accepted_original=((253, "old-253"), (254, "old-254")),
        ready_ids=(256, 257), completed=((256, "new-256"),),
        next_id=257, actor_user_id=7,
    )


@pytest.mark.parametrize("mutate", [
    lambda rows: setattr(rows[0], "provider_campaign_id", "wrong-original"),
    lambda rows: setattr(rows[2], "status", "READY"),
    lambda rows: setattr(rows[3], "status", "SUBMITTING"),
    lambda rows: setattr(rows[3], "submit_started_at", object()),
    lambda rows: setattr(rows[4], "provider_campaign_id", "duplicate-provider"),
])
def test_governed_skip_denies_tampered_original_or_pending(mutate):
    rows = [
        _governed_row(253, "SUBMITTED", provider_id="old-253"),
        _governed_row(254, "SUBMITTED", provider_id="old-254"),
        _governed_row(255, "PROVIDER_ERROR"),
        _governed_row(256, "READY"),
        _governed_row(257, "READY"),
    ]
    mutate(rows)
    with pytest.raises(governed_recovery.GovernedRecoveryBlocked):
        governed_recovery.verify_suffix(
            rows=rows, accepted_original=((253, "old-253"), (254, "old-254")),
            ready_ids=(256, 257), completed=(),
            next_id=256, actor_user_id=7,
        )


@pytest.mark.parametrize("completed,next_id", [
    ((), 257),
    (((256, "provider-256"),), 256),
    (((257, "provider-257"),), 257),
])
def test_governed_skip_requires_ordered_prefix(completed, next_id):
    rows = [
        _governed_row(253, "SUBMITTED", provider_id="old-253"),
        _governed_row(254, "SUBMITTED", provider_id="old-254"),
        _governed_row(255, "PROVIDER_ERROR"),
        _governed_row(256, "READY"),
        _governed_row(257, "READY"),
    ]
    with pytest.raises(governed_recovery.GovernedRecoveryBlocked):
        governed_recovery.verify_suffix(
            rows=rows, accepted_original=((253, "old-253"), (254, "old-254")),
            ready_ids=(256, 257), completed=completed,
            next_id=next_id, actor_user_id=7,
        )


def test_claim_failure_makes_zero_provider_requests(monkeypatch):
    provider = NS(create_campaign=Mock())
    def deny(**_kwargs):
        raise governed_recovery.GovernedRecoveryBlocked("quota changed")
    monkeypatch.setattr(governed_recovery, "claim_next", deny)
    with pytest.raises(governed_recovery.GovernedRecoveryBlocked, match="quota"):
        governed_recovery.send_next(
            review=NS(), child=NS(child_id=256),
            actor_user_id=7, completed=(), provider=provider, session=NS(),
        )
    provider.create_campaign.assert_not_called()


def test_governed_claim_is_durable_before_synthetic_provider(monkeypatch):
    claims = []
    provider_id = "synthetic-provider-256"
    def claim(**kwargs):
        claims.append(kwargs["child"].child_id)
        return NS()
    def provider_call(_dispatch):
        assert claims == [256]
        return NS(provider_campaign_id=provider_id,
                  deduplicated=False, response_metadata={}, http_status=200)
    persisted = []
    monkeypatch.setattr(governed_recovery, "claim_next", claim)
    monkeypatch.setattr(governed_recovery, "_persist_provider_success",
                        lambda **kwargs: persisted.append(kwargs))
    result = governed_recovery.send_next(
        review=NS(), child=NS(child_id=256, batch=NS(sucursal_canon="PASEO_LA_PAZ")),
        actor_user_id=7, completed=(),
        provider=NS(create_campaign=provider_call), session=NS(),
    )
    assert result == ("PASEO_LA_PAZ", "SUBMITTED", provider_id)
    assert persisted[0]["row_id"] == 256
    assert persisted[0]["provider_campaign_id"] == provider_id


def test_ambiguous_provider_result_is_persisted_and_stops(monkeypatch):
    # Reject unknown results exactly like governed D2c: never treat as accepted.
    def claim(**_kwargs):
        return NS()
    monkeypatch.setattr(governed_recovery, "claim_next", claim)
    saved = []
    monkeypatch.setattr(governed_recovery, "_persist_provider_failure",
                        lambda **kwargs: saved.append(kwargs))
    def uncertain(_dispatch):
        raise RuntimeError("network timeout after provider request")
    result = governed_recovery.send_next(
        review=NS(), child=NS(child_id=256, batch=NS(sucursal_canon="PASEO_LA_PAZ")),
        actor_user_id=7, completed=(),
        provider=NS(create_campaign=uncertain), session=NS(),
    )
    assert result[1:] == ("RECONCILIATION_REQUIRED", "UNEXPECTED_PROVIDER_RESULT")
    assert saved[0]["status"] == "RECONCILIATION_REQUIRED"
