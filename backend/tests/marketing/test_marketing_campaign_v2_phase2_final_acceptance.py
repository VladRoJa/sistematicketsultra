from __future__ import annotations

from pathlib import Path

from app.services import marketing_scheduler_worker as scheduler


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
CAMPAIGN_V2_FRONTEND = (
    REPO_ROOT / "frontend" / "src" / "app" / "marketing-campaign-v2"
)


def _read_backend(relative_path: str) -> str:
    return (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")


def test_phase2_final_m12_auto_capture_remains_disabled_and_fail_closed(
    monkeypatch,
):
    monkeypatch.delenv(
        scheduler.CAMPAIGN_V2_PROVIDER_STATS_ENABLED_ENV,
        raising=False,
    )
    assert scheduler._load_campaign_v2_provider_stats_scheduler_config() is None

    monkeypatch.setenv(
        scheduler.CAMPAIGN_V2_PROVIDER_STATS_ENABLED_ENV,
        "true",
    )
    for name in (
        scheduler.CAMPAIGN_V2_PROVIDER_STATS_INTERVAL_SECONDS_ENV,
        scheduler.CAMPAIGN_V2_PROVIDER_STATS_HORIZON_HOURS_ENV,
        scheduler.CAMPAIGN_V2_PROVIDER_STATS_MAX_PER_CYCLE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)

    try:
        scheduler._load_campaign_v2_provider_stats_scheduler_config()
    except RuntimeError as exc:
        assert "obligatorio" in str(exc)
    else:
        raise AssertionError(
            "M12 enabled sin cadence/horizon/max debe fallar cerrado."
        )


def test_phase2_final_reporting_boundary_stays_offline_m13_free_and_read_only():
    sources = "\n".join(
        _read_backend(path)
        for path in (
            "app/services/marketing_campaign_v2_reporting_service.py",
            "app/services/marketing_campaign_v2_reporting_excel_service.py",
            "app/services/marketing_campaign_v2_reporting_cost_service.py",
        )
    )

    for forbidden in (
        "get_provider_history_for_phones(",
        "get_campaign_v2_provider_stats(",
        "capture_campaign_v2_provider_stats_snapshot(",
        "requests.get(",
        "requests.post(",
        "httpx.get(",
        "httpx.post(",
        "active_session.add(",
        "active_session.delete(",
        "active_session.commit(",
        "active_session.flush(",
        "db.session.add(",
        "db.session.delete(",
        "db.session.commit(",
        "db.session.flush(",
    ):
        assert forbidden not in sources


def test_phase2_final_campaign_v2_backend_has_no_provider_write_surface():
    sources = "\n".join(
        _read_backend(path)
        for path in (
            "app/routes/marketing_campaign_v2_routes.py",
            "app/services/marketing_campaign_v2_audience_service.py",
            "app/services/marketing_campaign_v2_creation_service.py",
            "app/services/marketing_campaign_v2_provider_history_service.py",
            "app/services/marketing_campaign_v2_provider_stats_service.py",
            "app/services/marketing_campaign_v2_provider_stats_snapshot_service.py",
            "app/services/marketing_campaign_v2_reporting_service.py",
            "app/services/marketing_campaign_v2_reporting_excel_service.py",
        )
    )

    for forbidden in (
        "POST /v2/broadcast",
        "requests.post(",
        "httpx.post(",
        "graphql mutation",
        "mutation {",
    ):
        assert forbidden.lower() not in sources.lower()


def test_phase2_final_angular_has_no_provider_credentials_or_direct_send_surface():
    production_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CAMPAIGN_V2_FRONTEND.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".html"}
        and not path.name.endswith(".node-test.ts")
    )

    for forbidden in (
        "IVENTAS_CAMPAIGNS_API_KEY",
        "rest.iventas.mx",
        "/v2/broadcast",
        "localStorage",
    ):
        assert forbidden not in production_sources
