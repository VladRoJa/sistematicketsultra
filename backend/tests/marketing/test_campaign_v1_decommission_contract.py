from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MARKETING_ROUTES = ROOT / "app" / "routes" / "marketing_routes.py"
APP_INIT = ROOT / "app" / "__init__.py"
V2_AUDIENCE = ROOT / "app" / "services" / "marketing_campaign_v2_audience_service.py"


def test_campaign_v1_routes_are_not_exposed_by_marketing_blueprint():
    source = MARKETING_ROUTES.read_text(encoding="utf-8")

    assert "/reactivation/" not in source
    assert "MarketingReactivation" not in source
    assert 'marketing_bp.get("/dashboard")' in source
    assert 'marketing_bp.get("/inputs")' in source


def test_campaign_v1_auxiliary_blueprints_are_not_registered():
    source = APP_INIT.read_text(encoding="utf-8")

    for symbol in (
        "marketing_campaign_export_bp",
        "marketing_campaign_source_status_bp",
        "marketing_campaign_preview_detail_bp",
        "marketing_reactivation_outcome_bp",
        "marketing_campaign_delivery_bp",
    ):
        assert f"register_blueprint({symbol}" not in source


def test_campaign_v2_keeps_shared_iventas_status_resolver():
    source = V2_AUDIENCE.read_text(encoding="utf-8")

    assert "marketing_campaign_iventas_followup_service" in source
    assert "get_latest_iventas_status_by_phone" in source
