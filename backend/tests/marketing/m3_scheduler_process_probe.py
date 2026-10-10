"""One-shot M3 scheduler process QA. Never connect to provider or production.

Launched as three separate Python processes from PostgreSQL integration tests.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Direct script execution must still import the real backend package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sqlalchemy as sa
from flask import Flask

from app.extensions import db
from app.services import marketing_scheduler_worker as worker
from app.services.marketing_campaign_provider import (
    CampaignProviderRawCounts,
    CampaignProviderStats,
)
from app.services.marketing_campaign_v2_provider_stats_service import (
    MarketingCampaignV2ProviderStatsUpstreamError,
)
from app.services.marketing_campaign_v2_provider_stats_snapshot_service import (
    capture_campaign_v2_provider_stats_snapshot,
)


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) == 2 else None
    if stage not in ("fail-b", "recover", "steady"):
        raise ValueError("Unknown probe stage.")

    uri = os.getenv("M3_TEST_POSTGRES_URL", "")
    if not uri:
        raise ValueError("M3 isolated PostgreSQL URL is mandatory.")
    parsed = sa.engine.make_url(uri)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "m3_child_snapshots"
        or parsed.host not in ("127.0.0.1", "localhost")
        or parsed.username != "m3_test"
    ):
        raise ValueError("Refusing non-isolated PostgreSQL DB.")
    if os.getenv("CAMPAIGN_V2_PROVIDER_SEND_ENABLED", "").strip().lower() != "false":
        raise ValueError("Real provider sends must be explicitly disabled.")

    app = Flask("m3-probe")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=False,
    )
    db.init_app(app)

    def stats_for(phone: str) -> CampaignProviderStats:
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

    stats = {
        "ci-fake-batch-a": stats_for("mx10:6860000701"),
        "ci-fake-batch-b": stats_for("mx10:6860000702"),
    }
    calls: list[str] = []

    class FakeStatsProvider:
        def get_campaign_stats(self, provider_campaign_id: str) -> CampaignProviderStats:
            calls.append(provider_campaign_id)
            if stage == "fail-b" and provider_campaign_id == "ci-fake-batch-b":
                raise MarketingCampaignV2ProviderStatsUpstreamError(
                    "simulated-transient-upstream-error", retryable=True,
                )
            return stats[provider_campaign_id]

    fake_provider = FakeStatsProvider()
    now = datetime(2026, 10, 8, 19, tzinfo=timezone.utc) + (
        timedelta(hours={"fail-b": 0, "recover": 1, "steady": 2}[stage])
    )

    with app.app_context():
        # The worker must *not* capture when its flag is disabled.
        os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_ENABLED_ENV] = "false"
        assert worker._load_campaign_v2_provider_stats_scheduler_config() is None
        assert worker._run_campaign_v2_provider_stats_if_due(
            now=now, config=None,
        ) is None
        assert not calls

        # Only stats READ is enabled, never the provider SEND switch.
        os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_ENABLED_ENV] = "true"
        os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_INTERVAL_SECONDS_ENV] = "60"
        os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_HORIZON_HOURS_ENV] = "48"
        os.environ[worker.CAMPAIGN_V2_PROVIDER_STATS_MAX_PER_CYCLE_ENV] = "10"
        config = worker._load_campaign_v2_provider_stats_scheduler_config()
        assert config is not None

        production_capture = worker.run_campaign_v2_provider_stats_capture_cycle

        def local_read_only_provider_cycle(**kwargs):
            return production_capture(
                **kwargs,
                capture_func=lambda **capture_kwargs: (
                    capture_campaign_v2_provider_stats_snapshot(
                        **capture_kwargs,
                        provider_resolver=lambda _provider: fake_provider,
                    )
                ),
            )

        worker.run_campaign_v2_provider_stats_capture_cycle = local_read_only_provider_cycle
        session_remove = db.session.remove
        cleanup_calls: list[bool] = []

        def record_remove():
            cleanup_calls.append(True)
            return session_remove()

        db.session.remove = record_remove
        try:
            result = worker._run_campaign_v2_provider_stats_if_due(
                now=now, config=config,
            )
            assert result is not None
            assert worker._run_campaign_v2_provider_stats_if_due(
                now=now + timedelta(seconds=30), config=config,
            ) is None
            assert len(calls) == 2
        finally:
            worker.run_campaign_v2_provider_stats_capture_cycle = production_capture
            db.session.remove = session_remove
            db.session.remove()
        assert len(cleanup_calls) >= 1

    print(
        "M3_PROBE_JSON:" + json.dumps({
            "stage": stage,
            "selected": result.selected,
            "attempted": result.attempted,
            "created": result.created,
            "unchanged": result.unchanged,
            "failed": result.failed,
            "cleanup_calls": len(cleanup_calls),
            "provider_stats_calls": len(calls),
        }, sort_keys=True),
        flush=True,
    )


if __name__ == "__main__":
    main()
