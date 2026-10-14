"""Issue 856 B1: unverified identities cannot become quota or dispatch evidence."""
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes
from app.services.marketing_campaign_v2_portfolio_reference_service import (
    CampaignV2PortfolioReferenceValidationError,
    validate_reference,
)

BASE = {
    "business_id": "629679279215746",
    "display_name": None,
    "app_id": None,
    "source_reference": "Declarado por propietario 2026-10-14",
}


def test_valid_candidate_never_pretends_to_identify_a_waba():
    assert validate_reference(**BASE) == BASE
    result = validate_reference(
        business_id=" 1039061498449710 ",
        display_name=" Ultra Gimansios ",
        app_id=" 1600353821679164 ",
        source_reference=" Evidencia manual ",
    )
    assert result == {
        "business_id": "1039061498449710", "display_name": "Ultra Gimansios",
        "app_id": "1600353821679164", "source_reference": "Evidencia manual",
    }


@pytest.mark.parametrize("updates", [
    {"business_id": "act_1394543581400837"},
    {"business_id": "0"},
    {"business_id": "none"},
    {"business_id": 123},
    {"display_name": "X" * 161},
    {"app_id": "not-an-app"},
    {"app_id": 123},
    {"source_reference": ""},
    {"source_reference": "s" * 256},
])
def test_invalid_reference_rejected(updates):
    with pytest.raises(CampaignV2PortfolioReferenceValidationError):
        validate_reference(**{**BASE, **updates})


def _app_and_headers():
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = version("werkzeug")
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="campaign-v2-portfolio-test")
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("method", ["get", "post"])
def test_portfolio_api_requires_jwt(method):
    client, _ = _app_and_headers()
    path = "/api/marketing/campaigns-v2/dispatch/portfolio-references"
    response = getattr(client, method)(path, json=BASE if method == "post" else None)
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["get", "post"])
def test_portfolio_api_requires_global_dispatch_permission(method):
    client, headers = _app_and_headers()
    path = "/api/marketing/campaigns-v2/dispatch/portfolio-references"
    restricted = SimpleNamespace(is_global=False, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), restricted)), \
         patch.object(routes, "list_portfolio_references") as read, \
         patch.object(routes, "register_portfolio_reference") as write:
        response = getattr(client, method)(
            path, headers=headers, json=BASE if method == "post" else None,
        )
    assert response.status_code == 403
    read.assert_not_called()
    write.assert_not_called()


def test_global_operator_reads_unverified_records():
    client, headers = _app_and_headers()
    permitted = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), permitted)), \
         patch.object(routes, "list_portfolio_references", return_value={"rows": []}) as read:
        response = client.get(
            "/api/marketing/campaigns-v2/dispatch/portfolio-references",
            headers=headers,
        )
    assert response.status_code == 200
    assert response.get_json() == {"rows": []}
    read.assert_called_once()


def test_global_operator_creates_unverified_reference_not_a_channel_binding():
    client, headers = _app_and_headers()
    permitted = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), permitted)), \
         patch.object(routes, "register_portfolio_reference", return_value={
             "business_id": BASE["business_id"], "verification_status": "UNVERIFIED",
             "linked_channel_count": 0,
         }) as register:
        response = client.post(
            "/api/marketing/campaigns-v2/dispatch/portfolio-references",
            headers=headers, json=BASE,
        )
    assert response.status_code == 201
    assert response.get_json()["verification_status"] == "UNVERIFIED"
    assert register.call_args.kwargs["actor_user_id"] == 7
    assert "channel_id" not in register.call_args.kwargs
