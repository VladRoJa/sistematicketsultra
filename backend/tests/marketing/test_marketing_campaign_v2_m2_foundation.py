from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.marketing import MarketingCampaignV2ProviderCampaignORM


def test_m2_provider_campaign_has_submit_audit_fields():
    columns = MarketingCampaignV2ProviderCampaignORM.__table__.c

    assert columns.submit_started_at.nullable is True
    assert columns.provider_deduplicated.nullable is True
    assert columns.request_snapshot_json.nullable is False
    assert columns.provider_response_json.nullable is False


def test_m2_migration_extends_campaign_v2_head():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "d2f8a4c6b1e7_extend_campaign_v2_m2_submit_audit.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campaign_v2_m2_submit_audit",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "d2f8a4c6b1e7"
    assert module.down_revision == "c1f7e9a4b6d2"


def test_m2_kill_switch_default_is_off_in_config_source():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "config.py"
    ).read_text(encoding="utf-8")

    assert '"CAMPAIGN_V2_PROVIDER_SEND_ENABLED"' in source
    assert '"false"' in source
    assert '"IVENTAS_CAMPAIGN_SEND_API_KEY"' in source
