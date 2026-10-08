"""Disposable Docker Compose probe running the actual marketing scheduler loop.

No iVentas/Meta HTTP, no production DB, no real broadcast submission.
Used only by the isolated M3 CI workflow.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

# Direct QA script execution must resolve the actual backend package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sqlalchemy as sa
from flask import Flask

from app.extensions import db
from app.services import marketing_scheduler_worker as worker
from app.services.marketing_campaign_provider import CampaignProviderRawCounts, CampaignProviderStats
from app.services.marketing_campaign_v2_provider_stats_service import (
    MarketingCampaignV2ProviderStatsUpstreamError,
)
from app.services.marketing_campaign_v2_provider_stats_snapshot_service import (
    capture_campaign_v2_provider_stats_snapshot,
)

HEALTH_PATH = Path("/tmp/m3-marketing-scheduler-health.json")


def main() -> None:
    url = os.environ.get("M3_TEST_POSTGRES_URL", "")
    parsed = sa.engine.make_url(url)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "m3_child_snapshots"
        or parsed.host not in ("127.0.0.1", "localhost")
        or parsed.username != "m3_test"
    ):
        raise RuntimeError("M3 Compose probe refuses any non-isolated database")

    if os.environ.get("CAMPAIGN_V2_PROVIDER_SEND_ENABLED", "").lower() != "false":
        raise RuntimeError("The broadcast kill switch must remain OFF")

    phase = os.environ.get("M3_QA_PHASE", "")
    if phase not in ("fail-b", "recover", "steady"):
        raise RuntimeError("Unknown isolated QA phase")

    app = Flask("m3-marketing-scheduler-qa")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=False,
    )
    db.init_app(app)

    def make_stats(phone: str) -> CampaignProviderStats:
        return CampaignProviderStats(
            analytics_status="ok",
            analytics={"responders": 0},
            raw_counts=CampaignProviderRawCounts(
                successful=1, failed=0, sent=0, delivered=1,
                viewed=0, answered=0, interaction_groups=0, interaction_items=0,
            ),
            successful_phones=frozenset({phone}),
            failed_phones=frozenset(),
            sent_phones=frozenset(),
            delivered_phones=frozenset({phone}),
            viewed_phones=frozenset(),
            button_interactions=(),
        )

    fake_stats = {
        "ci-fake-batch-a": make_stats("mx10:6860000701"),
        "ci-fake-batch-b": make_stats("mx10:6860000702"),
    }

    class FakeProvider:
        def get_campaign_stats(self, provider_campaign_id: str) -> CampaignProviderStats:
            if provider_campaign_id not in fake_stats:
                raise RuntimeError("Unexpected provider identity in isolated QA")
            if phase == "fail-b" and provider_campaign_id == "ci-fake-batch-b":
                raise MarketingCampaignV2ProviderStatsUpstreamError(
                    "simulated error, no external API", retryable=True,
                )
            return fake_stats[provider_campaign_id]

    provider = FakeProvider()
    os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_ENABLED_ENV] = "true"
    os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_INTERVAL_SECONDS_ENV] = "1"
    os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_HORIZON_HOURS_ENV] = "48"
    os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_MAX_PER_CYCLE_ENV] = "10"
    os.environ["MARKETING_SCHEDULER_POLL_SECONDS"] = "10"
    os.environ["MARKETING_SCHEDULER_RUN_TIMES"] = "00:00"
    os.environ["MARKETING_SCHEDULER_TZ"] = "America/Tijuana"

    # Never execute the unrelated outbound marketing sync jobs.
    worker._resolve_due_slot = lambda **_kwargs: None
    worker.get_secondary_job_block_reason = lambda _now: None
    real_cycle = worker.run_campaign_v2_provider_stats_capture_cycle

    def safe_cycle(**kwargs):
        return real_cycle(
            **kwargs,
            capture_func=lambda **kw: capture_campaign_v2_provider_stats_snapshot(
                **kw, provider_resolver=lambda _name: provider,
            ),
        )

    worker.run_campaign_v2_provider_stats_capture_cycle = safe_cycle
    real_run_if_due = worker._run_campaign_v2_provider_stats_if_due
    tick_count = 0

    def instrumented_run_if_due(*, now, config):
        nonlocal tick_count
        result = real_run_if_due(now=now, config=config)
        tick_count += 1
        payload = {
            "phase": phase,
            "ticks": tick_count,
            "epoch": time.time(),
            "created": result.created if result else None,
            "unchanged": result.unchanged if result else None,
            "failed": result.failed if result else None,
        }
        HEALTH_PATH.write_text(json.dumps(payload), encoding="utf-8")
        print("M3_COMPOSE_CYCLE:" + json.dumps(payload, sort_keys=True), flush=True)
        return result

    worker._run_campaign_v2_provider_stats_if_due = instrumented_run_if_due

    # Use deterministic dates to select the synthetic campaign, but real 10s
    # poll intervals and real DB persistence across Docker Compose restarts.
    def test_clock():
        return datetime(2026, 10, 8, 19, tzinfo=timezone.utc) + timedelta(
            hours=tick_count,
        )

    worker._now_local = test_clock
    worker._SHOULD_STOP = False
    worker._NEXT_PROVIDER_STATS_CAPTURE_AT = None
    signal.signal(signal.SIGTERM, worker._handle_stop)
    signal.signal(signal.SIGINT, worker._handle_stop)

    with app.app_context():
        worker.run_scheduler_loop()


if __name__ == "__main__":
    main()
