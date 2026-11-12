"""Synthetic worker integration: uncertain job does not block a separate job."""
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from app.services import marketing_campaign_v2_background_worker as worker


def test_worker_loop_continues_an_independent_job_after_uncertain_failure(monkeypatch):
    # One job may end in review, but the next job must still be claimed.
    # No provider HTTP, threads, timers or production DB connections.
    session = MagicMock()
    monkeypatch.setattr(worker.db, "session", session)
    monkeypatch.setattr(worker, "STOP", False)
    monkeypatch.setattr(worker, "_enabled", lambda config: True)
    monkeypatch.setattr(worker, "expire_stale_running", lambda **kwargs: None)
    remaining = iter([(101, 1), (102, 1)])
    def claim(**kwargs):
        return next(remaining)
    monkeypatch.setattr(worker, "claim_next_queued", claim)
    calls = []
    def run_child(**kwargs):
        calls.append(kwargs["job_id"])
        if kwargs["job_id"] == 101:
            raise RuntimeError("Synthetic ambiguous provider outcome")
        worker.STOP = True
    monkeypatch.setattr(worker, "process_claimed_job", run_child)
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)

    worker.run_loop(app=NS(config={}), poll_seconds=2)

    assert calls == [101, 102]
    assert session.rollback.call_count == 1
    assert session.remove.call_count == 2
