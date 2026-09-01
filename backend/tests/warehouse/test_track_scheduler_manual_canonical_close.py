from datetime import date, datetime
from types import SimpleNamespace

import pytest

import app.warehouse.scheduler.track_scheduler_worker as worker


def test_scheduler_decides_automatic_canonical_close_request_when_ready(
    monkeypatch: pytest.MonkeyPatch,
):
    now_local = datetime(
        2026,
        9,
        1,
        8,
        5,
        tzinfo=worker.TRACK_TIMEZONE,
    )

    for env_name in (
        "TRACK_PREVIEW_START_HOUR",
        "TRACK_PREVIEW_END_HOUR",
        "TRACK_NIGHTLY_BASE_HOUR",
        "TRACK_NIGHTLY_BASE_MINUTE",
        "TRACK_NIGHTLY_RETRY_HOUR",
        "TRACK_NIGHTLY_RETRY_MINUTE",
        "TRACK_CLOSE_LOOKBACK_DAYS",
    ):
        monkeypatch.delenv(env_name, raising=False)

    expected_track_date = date(2026, 8, 31)

    monkeypatch.setattr(
        worker,
        "_find_automatic_canonical_close_date",
        lambda *, today, lookback_days: expected_track_date,
        raising=False,
    )

    decision = worker.decide_track_scheduler_action(
        now_local
    )

    assert decision is not None
    assert decision.action == "request_cierre_canonico"
    assert decision.track_date == expected_track_date
    assert (
        decision.reason
        == "exact_agregadoras_available_for_closed_day"
    )


def test_automatic_close_finder_selects_ready_closed_day(
    monkeypatch: pytest.MonkeyPatch,
):
    target_date = date(2026, 8, 31)

    def fake_has_success_current_version(
        *,
        track_date,
        version_type,
    ):
        assert track_date == target_date

        return (
            version_type == "base_nocturna_canonica"
        )

    monkeypatch.setattr(
        worker,
        "_has_success_current_version",
        fake_has_success_current_version,
    )

    monkeypatch.setattr(
        worker,
        "get_latest_track_canonical_close_version",
        lambda *, track_date: None,
    )

    monkeypatch.setattr(
        worker,
        "resolve_exact_agregadoras_snapshot_status_for_date",
        lambda *, business_date: {
            "business_date": business_date.isoformat(),
            "has_wellhub": True,
            "has_totalpass": True,
            "is_ready": True,
        },
    )

    result = worker._find_automatic_canonical_close_date(
        today=date(2026, 9, 1),
        lookback_days=7,
    )

    assert result == target_date

def test_pending_close_executor_returns_none_when_no_request(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    def fake_claim(*, auto_commit):
        assert auto_commit is True
        calls.append("claim")
        return None

    def forbidden_executor(**_kwargs):
        raise AssertionError(
            "No debe ejecutarse cierre sin solicitud reclamada."
        )

    monkeypatch.setattr(
        worker,
        "claim_next_pending_track_canonical_close",
        fake_claim,
    )
    monkeypatch.setattr(
        worker,
        "run_requested_track_canonical_close",
        forbidden_executor,
    )

    result = (
        worker.execute_pending_track_canonical_close_request()
    )

    assert result is None
    assert calls == ["claim"]


def test_pending_close_executor_claims_and_executes_exact_version_id(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    request_version = SimpleNamespace(
        id=321,
        track_date=date(2026, 7, 31),
        requested_by="admin_test",
        status="running",
        is_current=False,
    )

    def fake_claim(*, auto_commit):
        assert auto_commit is True
        calls.append(("claim", auto_commit))
        return request_version

    def fake_executor(*, track_daily_version_id):
        calls.append(
            ("execute", track_daily_version_id)
        )

        return {
            "status": "completed",
            "track_date": "2026-07-31",
            "track_daily_version": {
                "id": track_daily_version_id,
                "version_type": "cierre_canonico",
                "status": "success",
                "is_current": True,
            },
        }

    monkeypatch.setattr(
        worker,
        "claim_next_pending_track_canonical_close",
        fake_claim,
    )
    monkeypatch.setattr(
        worker,
        "run_requested_track_canonical_close",
        fake_executor,
    )

    result = (
        worker.execute_pending_track_canonical_close_request()
    )

    assert calls == [
        ("claim", True),
        ("execute", 321),
    ]

    assert result["status"] == "completed"
    assert result["track_date"] == "2026-07-31"
    assert result["track_daily_version"]["id"] == 321

def test_preview_operativo_starts_at_5am_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    for env_name in (
        "TRACK_PREVIEW_START_HOUR",
        "TRACK_PREVIEW_END_HOUR",
        "TRACK_NIGHTLY_BASE_HOUR",
        "TRACK_NIGHTLY_BASE_MINUTE",
        "TRACK_NIGHTLY_RETRY_HOUR",
        "TRACK_NIGHTLY_RETRY_MINUTE",
    ):
        monkeypatch.delenv(env_name, raising=False)

    cases = (
        (4, None),
        (5, "preview_operativo"),
        (6, "preview_operativo"),
        (7, "preview_operativo"),
    )

    for hour, expected_action in cases:
        now_local = datetime(
            2026,
            8,
            17,
            hour,
            0,
            tzinfo=worker.TRACK_TIMEZONE,
        )

        decision = worker.decide_track_scheduler_action(
            now_local
        )

        actual_action = (
            decision.action
            if decision is not None
            else None
        )

        assert actual_action == expected_action
