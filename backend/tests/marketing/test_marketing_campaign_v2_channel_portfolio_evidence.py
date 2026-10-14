"""Issue #856 B2: prevent candidate Business ID assertions bypassing dispatch rules."""
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes
from app.services.marketing_campaign_v2_channel_portfolio_evidence_service import (
    CampaignV2ChannelPortfolioValidationError,
    CampaignV2ChannelPortfolioConflictError,
    normalize_claim,
)

BASE = {
    "provider_channel_id": "provider-001",
    "business_id": "629679279215746",
    "waba_id": None,
    "state": "DECLARED",
    "evidence_kind": "OPERATOR_STATEMENT",
    "source_reference": "Operador referencia 2026-10-14",
    "expected_revision_id": None,
}


def test_claim_valid_and_explicitly_unverified():
    assert normalize_claim(**BASE) == BASE
    withdrawn = normalize_claim(**{
        **BASE, "state": "WITHDRAWN",
        "business_id": None, "waba_id": None, "expected_revision_id": 23,
    })
    assert withdrawn["business_id"] is None
    assert withdrawn["expected_revision_id"] == 23


@pytest.mark.parametrize("changes", [
    {"provider_channel_id": ""},
    {"business_id": "act_123456789"},
    {"business_id": "0"},
    {"waba_id": "not-a-waba"},
    {"state": "VERIFIED"},
    {"state": "WITHDRAWN", "waba_id": "123456789"},
    {"state": "WITHDRAWN", "business_id": "123456789"},
    {"evidence_kind": "SECRET"},
    {"source_reference": ""},
    {"source_reference": "X" * 256},
    {"expected_revision_id": 0},
    {"expected_revision_id": True},
])
def test_bad_claim_rejected(changes):
    with pytest.raises(CampaignV2ChannelPortfolioValidationError):
        normalize_claim(**{**BASE, **changes})


def _client():
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = version("werkzeug")
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="v2-channel-evidence-test")
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("method", ["get", "post"])
def test_evidence_requires_jwt(method):
    client, _ = _client()
    endpoint = "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence"
    response = getattr(client, method)(endpoint, json=BASE if method == "post" else None)
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["get", "post"])
def test_evidence_requires_global_dispatch_access(method):
    client, headers = _client()
    restricted = SimpleNamespace(is_global=False, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), restricted)), \
         patch.object(routes, "list_channel_portfolio_evidence") as read, \
         patch.object(routes, "register_channel_portfolio_evidence") as save:
        response = getattr(client, method)(
            "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence",
            headers=headers, json=BASE if method == "post" else None,
        )
    assert response.status_code == 403
    read.assert_not_called()
    save.assert_not_called()


def test_global_read_does_not_write():
    client, headers = _client()
    access = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), access)), \
         patch.object(routes, "list_channel_portfolio_evidence", return_value={
             "rows": [], "history": [], "history_is_limited": False,
         }) as read, \
         patch.object(routes, "register_channel_portfolio_evidence") as save:
        response = client.get(
            "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence",
            headers=headers,
        )
    assert response.status_code == 200
    assert response.get_json()["history"] == []
    read.assert_called_once()
    save.assert_not_called()


def test_global_write_carries_authenticated_actor_and_expected_revision():
    client, headers = _client()
    access = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), access)), \
         patch.object(routes, "register_channel_portfolio_evidence", return_value={
             "revision_id": 24, "state": "DECLARED", "api_verified": False,
         }) as save:
        response = client.post(
            "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence",
            json={**BASE, "expected_revision_id": 23}, headers=headers,
        )
    assert response.status_code == 201
    assert response.get_json()["api_verified"] is False
    assert save.call_args.kwargs["actor_user_id"] == 7
    assert save.call_args.kwargs["expected_revision_id"] == 23


def test_stale_revision_returns_409_without_provider_call():
    client, headers = _client()
    access = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), access)), \
         patch.object(routes, "register_channel_portfolio_evidence",
                      side_effect=CampaignV2ChannelPortfolioConflictError("stale")):
        response = client.post(
            "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence",
            json=BASE, headers=headers,
        )
    assert response.status_code == 409
