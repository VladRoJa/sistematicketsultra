from datetime import date, datetime
from types import SimpleNamespace

import pytest

import app.warehouse.scheduler.track_scheduler_worker as worker


def test_scheduler_no_longer_decides_automatic_close_at_old_close_minute(
    monkeypatch: pytest.MonkeyPatch,
):
    # :05 era uno de los minutos donde el scheduler viejo buscaba
    # autónomamente días históricos para cerrar.
    now_local = datetime(
        2026,
        8,
        7,
        12,
        5,
        tzinfo=worker.TRACK_TIMEZONE,
    )

    # Aislamos variables de horario para usar los defaults conocidos.
    for env_name in (
        "TRACK_PREVIEW_START_HOUR",
        "TRACK_PREVIEW_END_HOUR",
        "TRACK_NIGHTLY_BASE_HOUR",
        "TRACK_NIGHTLY_BASE_MINUTE",
        "TRACK_NIGHTLY_RETRY_HOUR",
        "TRACK_NIGHTLY_RETRY_MINUTE",
    ):
        monkeypatch.delenv(env_name, raising=False)

    decision = worker.decide_track_scheduler_action(
        now_local
    )

    assert decision is None


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
