from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services import marketing_scheduler_worker as worker


TIJUANA = ZoneInfo("America/Tijuana")


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    worker._COMPLETED_SLOTS.clear()
    worker._IVENTAS_COMPLETED_SLOTS.clear()
    worker._META_COMPLETED_SLOTS.clear()
    worker._NEXT_RETRY_BY_SLOT.clear()

    yield

    worker._COMPLETED_SLOTS.clear()
    worker._IVENTAS_COMPLETED_SLOTS.clear()
    worker._META_COMPLETED_SLOTS.clear()
    worker._NEXT_RETRY_BY_SLOT.clear()


def test_parse_run_times_uses_expected_defaults(
    monkeypatch,
):
    monkeypatch.delenv(
        "MARKETING_SCHEDULER_RUN_TIMES",
        raising=False,
    )
    monkeypatch.delenv(
        "MARKETING_SCHEDULER_RUN_HOURS",
        raising=False,
    )

    assert worker._parse_run_times() == (
        (8, 20),
        (12, 20),
        (16, 20),
        (20, 20),
    )


def test_parse_run_times_accepts_configurable_values(
    monkeypatch,
):
    monkeypatch.setenv(
        "MARKETING_SCHEDULER_RUN_TIMES",
        "20:20,08:20,12:20,16:20,12:20",
    )

    assert worker._parse_run_times() == (
        (8, 20),
        (12, 20),
        (16, 20),
        (20, 20),
    )


def test_parse_run_times_supports_legacy_run_hours(
    monkeypatch,
):
    monkeypatch.delenv(
        "MARKETING_SCHEDULER_RUN_TIMES",
        raising=False,
    )
    monkeypatch.setenv(
        "MARKETING_SCHEDULER_RUN_HOURS",
        "20,8,12,16",
    )

    assert worker._parse_run_times() == (
        (8, 0),
        (12, 0),
        (16, 0),
        (20, 0),
    )


def test_resolve_due_slot_runs_latest_elapsed_slot():
    now = datetime(
        2026,
        8,
        24,
        9,
        15,
        tzinfo=TIJUANA,
    )

    result = worker._resolve_due_slot(
        now=now,
        run_times=(
            (8, 20),
            (12, 20),
            (16, 20),
            (20, 20),
        ),
    )

    assert result == (
        date(2026, 8, 24),
        8,
        20,
    )


def test_resolve_due_slot_does_not_run_before_first_slot():
    now = datetime(
        2026,
        8,
        24,
        8,
        19,
        tzinfo=TIJUANA,
    )

    result = worker._resolve_due_slot(
        now=now,
        run_times=(
            (8, 20),
            (12, 20),
            (16, 20),
            (20, 20),
        ),
    )

    assert result is None


def test_resolve_due_slot_does_not_repeat_completed_slot():
    now = datetime(
        2026,
        8,
        24,
        9,
        15,
        tzinfo=TIJUANA,
    )

    slot_key = (
        date(2026, 8, 24),
        8,
        20,
    )

    worker._COMPLETED_SLOTS.add(
        slot_key
    )

    result = worker._resolve_due_slot(
        now=now,
        run_times=(
            (8, 20),
            (12, 20),
            (16, 20),
            (20, 20),
        ),
    )

    assert result is None


def test_resolve_due_slot_waits_for_retry_window():
    slot_key = (
        date(2026, 8, 24),
        8,
        20,
    )

    retry_at = datetime(
        2026,
        8,
        24,
        9,
        30,
        tzinfo=TIJUANA,
    )

    worker._NEXT_RETRY_BY_SLOT[
        slot_key
    ] = retry_at

    before_retry = worker._resolve_due_slot(
        now=retry_at - timedelta(minutes=1),
        run_times=(
            (8, 20),
            (12, 20),
            (16, 20),
            (20, 20),
        ),
    )

    at_retry = worker._resolve_due_slot(
        now=retry_at,
        run_times=(
            (8, 20),
            (12, 20),
            (16, 20),
            (20, 20),
        ),
    )

    assert before_retry is None
    assert at_retry == slot_key


def test_resolve_due_slot_moves_to_newer_scheduled_cut():
    now = datetime(
        2026,
        8,
        24,
        12,
        25,
        tzinfo=TIJUANA,
    )

    result = worker._resolve_due_slot(
        now=now,
        run_times=(
            (8, 20),
            (12, 20),
            (16, 20),
            (20, 20),
        ),
    )

    assert result == (
        date(2026, 8, 24),
        12,
        20,
    )

def test_load_meta_accounts_requires_and_loads_five_accounts(
    monkeypatch,
):
    expected = (
        (
            "META_ACCESS_TOKEN_CP01_CP03",
            "META_AD_ACCOUNT_CP01",
            "token-shared",
            "act_cp01",
        ),
        (
            "META_ACCESS_TOKEN_CP01_CP03",
            "META_AD_ACCOUNT_CP03",
            "token-shared",
            "act_cp03",
        ),
        (
            "META_ACCESS_TOKEN_ULTRAGYM2",
            "META_AD_ACCOUNT_ULTRAGYM2",
            "token-2",
            "act_2",
        ),
        (
            "META_ACCESS_TOKEN_ULTRAGYM3",
            "META_AD_ACCOUNT_ULTRAGYM3",
            "token-3",
            "act_3",
        ),
        (
            "META_ACCESS_TOKEN_ULTRAGYM4",
            "META_AD_ACCOUNT_ULTRAGYM4",
            "token-4",
            "act_4",
        ),
    )

    for (
        token_env,
        account_env,
        token_value,
        account_value,
    ) in expected:
        monkeypatch.setenv(
            token_env,
            token_value,
        )
        monkeypatch.setenv(
            account_env,
            account_value,
        )

    accounts = worker._load_meta_accounts()

    assert len(accounts) == 5

    assert tuple(
        account.account_id
        for account in accounts
    ) == (
        "act_cp01",
        "act_cp03",
        "act_2",
        "act_3",
        "act_4",
    )


def test_load_meta_accounts_fails_if_one_account_is_missing(
    monkeypatch,
):
    for (
        token_env,
        account_env,
    ) in worker.DEFAULT_META_ACCOUNT_BINDINGS:
        monkeypatch.setenv(
            token_env,
            "test-token",
        )
        monkeypatch.setenv(
            account_env,
            "act_test",
        )

    monkeypatch.delenv(
        "META_AD_ACCOUNT_ULTRAGYM4",
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="META_AD_ACCOUNT_ULTRAGYM4",
    ):
        worker._load_meta_accounts()


def test_execute_marketing_sync_can_retry_only_meta(
    monkeypatch,
):
    calls = {
        "iventas": 0,
        "meta": 0,
    }

    def fake_iventas_sync(**kwargs):
        calls["iventas"] += 1
        raise AssertionError(
            "iVentas no debía ejecutarse en este retry."
        )

    class MetaResult:
        sync_run_id = 99
        status = "COMPLETED"
        is_canonical = True
        accounts_completed = 5
        accounts_requested = 5
        insights_unique = 123

    def fake_meta_sync(**kwargs):
        calls["meta"] += 1
        return MetaResult()

    monkeypatch.setattr(
        worker,
        "sync_iventas_full_run",
        fake_iventas_sync,
    )
    monkeypatch.setattr(
        worker,
        "sync_meta_full_run",
        fake_meta_sync,
    )
    monkeypatch.setattr(
        worker,
        "_load_meta_accounts",
        lambda: (),
    )
    monkeypatch.setattr(
        worker.db.session,
        "remove",
        lambda: None,
    )

    result = worker.execute_marketing_sync(
        business_date=date(2026, 8, 24),
        run_iventas=False,
        run_meta=True,
    )

    assert calls == {
        "iventas": 0,
        "meta": 1,
    }
    assert result.iventas_completed is True
    assert result.meta_completed is True
    assert result.completed is True


def test_retry_flags_only_failed_source():
    slot_key = (
        date(2026, 8, 24),
        8,
        20,
    )

    worker._IVENTAS_COMPLETED_SLOTS.add(
        slot_key
    )

    run_iventas = (
        slot_key
        not in worker._IVENTAS_COMPLETED_SLOTS
    )
    run_meta = (
        slot_key
        not in worker._META_COMPLETED_SLOTS
    )

    assert run_iventas is False
    assert run_meta is True
