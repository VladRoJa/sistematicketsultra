"""Issue #856 D1: quota admin route permission and provider independence."""
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes


@pytest.fixture()
def client():
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = version("werkzeug")
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-quota-test",
                      CAMPAIGN_V2_PROVIDER_SEND_ENABLED=False)
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def global_access():
    return SimpleNamespace(
        is_global=True, branch_ids=(), can_manage_campaigns=True,
        can_preflight_campaigns=True, can_manage_dispatch_config=True,
        can_send_campaigns=True,
    )


@pytest.fixture()
def partial_access():
    return SimpleNamespace(
        is_global=False, branch_ids=(11,), can_manage_campaigns=True,
        can_preflight_campaigns=True, can_manage_dispatch_config=True,
        can_send_campaigns=False,
    )


def auth(access):
    return patch.object(routes, "_resolve_request_access",
                        return_value=(SimpleNamespace(id=7), access))


def test_quota_admin_get_global_only(client, global_access, partial_access):
    browser, headers = client
    with auth(partial_access), patch.object(routes, "list_quota_evidence") as list_evidence:
        response = browser.get("/api/marketing/campaigns-v2/dispatch/quota-evidence",
                               headers=headers)
    assert response.status_code == 403
    list_evidence.assert_not_called()
    with auth(global_access), patch.object(
        routes, "list_quota_evidence",
        return_value={"policies":[],"attestations":[]},
    ) as list_evidence:
        response = browser.get("/api/marketing/campaigns-v2/dispatch/quota-evidence",
                               headers=headers)
    assert response.status_code == 200
    assert response.json == {"policies":[],"attestations":[]}
    list_evidence.assert_called_once()


def test_quota_registration_traces_authenticated_actor_no_provider(
    client, global_access,
):
    browser, headers = client
    payload = {
        "provider_channel_id":"synthetic-channel", "portfolio_key":"shared",
        "account_key":"synthetic-account", "phone_alias":"synthetic-number",
        "nominal_channel_limit":250, "reset_timezone":"America/Tijuana",
        "source_reference":"synthetic contract",
    }
    with auth(global_access), patch.object(
        routes, "register_quota_policy", return_value={"revision_id":2},
    ) as register, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post("/api/marketing/campaigns-v2/dispatch/quota-policies",
                                json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json["revision_id"] == 2
    assert register.call_args.kwargs["actor_user_id"] == 7
    provider.assert_not_called()


def test_quota_attestation_rejects_unknown_fields_and_partial_scope(
    client, global_access, partial_access,
):
    browser, headers = client
    with auth(global_access), patch.object(routes,"register_quota_capacity") as register:
        response = browser.post(
            "/api/marketing/campaigns-v2/dispatch/quota-attestations",
            json={"scope_kind":"PORTFOLIO","scope_key":"shared",
                  "send_enabled":True},
            headers=headers,
        )
    assert response.status_code == 400
    register.assert_not_called()
    with auth(partial_access), patch.object(routes,"register_quota_capacity") as register:
        response = browser.post(
            "/api/marketing/campaigns-v2/dispatch/quota-attestations",
            json={"scope_kind":"PORTFOLIO","scope_key":"shared"},
            headers=headers,
        )
    assert response.status_code == 403
    register.assert_not_called()


def test_approval_needs_both_capabilities_and_global_scope(
    client, global_access, partial_access,
):
    browser, headers = client
    endpoint = "/api/marketing/campaigns-v2/99/dispatch/approval"
    payload = {
        "template_id": 2, "expected_dispatch_fingerprint": "a" * 64,
        "expected_recipients": 12, "expected_total_mxn": "3.60",
    }
    with auth(partial_access), patch.object(routes, "approve_dispatch_reservation") as approve:
        response = browser.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 403
    approve.assert_not_called()

    no_send = SimpleNamespace(**vars(global_access))
    no_send.can_send_campaigns = False
    with auth(no_send), patch.object(routes, "approve_dispatch_reservation") as approve:
        response = browser.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 403
    approve.assert_not_called()

    with auth(global_access), patch.object(
        routes, "approve_dispatch_reservation",
        return_value={"status": "RESERVED_NOT_DISPATCHED", "send_authorized": False},
    ) as approve, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json["send_authorized"] is False
    assert approve.call_args.kwargs["actor_user_id"] == 7
    provider.assert_not_called()


def test_approval_rejects_client_supplied_send_override(client, global_access):
    browser, headers = client
    with auth(global_access), patch.object(routes, "approve_dispatch_reservation") as approve:
        response = browser.post(
            "/api/marketing/campaigns-v2/99/dispatch/approval",
            json={"template_id": 2, "send_enabled": True},
            headers=headers,
        )
    assert response.status_code == 400
    approve.assert_not_called()
