"""Issue #856 E: negative release gates. No live provider or production database.

Every positive-switch scenario mocks the provider and dispatch service. Tests are
purposefully not a substitute for a separately authorized, real single-child canary.
"""
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes

ENDPOINT = "/api/marketing/campaigns-v2/99/dispatch/execute"
GOOD = {"execution_id": 41, "child_id": 100, "expected_manifest_digest": "a" * 64}


@pytest.fixture()
def api():
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = version("werkzeug")
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="synthetic-issue-856-e",
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=False,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=False,
        IVENTAS_CAMPAIGN_SEND_API_KEY="synthetic-never-send",
    )
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def access(**overrides):
    attrs = {
        "is_global": True, "can_manage_dispatch_config": True,
        "can_send_campaigns": True, "can_manage_campaigns": True,
        "can_preflight_campaigns": True, "branch_ids": (),
    }
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


@pytest.mark.parametrize("send,governed", [
    (False, False), (False, True), (True, False),
])
def test_each_off_switch_blocks_before_provider_construction_or_service(
    api, send, governed,
):
    browser, headers = api
    browser.application.config.update(
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=send,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=governed,
    )
    with patch.object(routes, "_resolve_request_access",
                      return_value=(SimpleNamespace(id=47), access())), \
         patch.object(routes, "IVentasBroadcastProvider") as provider, \
         patch.object(routes, "execute_governed_child") as execute:
        response = browser.post(ENDPOINT, headers=headers, json=GOOD)
    assert response.status_code == 423
    provider.assert_not_called()
    execute.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"is_global": False}, {"can_manage_dispatch_config": False},
    {"can_send_campaigns": False},
])
def test_permissions_deny_even_if_both_flags_on(api, changes):
    browser, headers = api
    browser.application.config.update(
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=True,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=True,
    )
    with patch.object(routes, "_resolve_request_access",
                      return_value=(SimpleNamespace(id=47), access(**changes))), \
         patch.object(routes, "IVentasBroadcastProvider") as provider, \
         patch.object(routes, "execute_governed_child") as execute:
        response = browser.post(ENDPOINT, headers=headers, json=GOOD)
    assert response.status_code == 403
    provider.assert_not_called()
    execute.assert_not_called()


def test_jwt_required_without_query_or_provider(api):
    browser, _ = api
    with patch.object(routes, "IVentasBroadcastProvider") as provider, \
         patch.object(routes, "execute_governed_child") as execute:
        response = browser.post(ENDPOINT, json=GOOD)
    assert response.status_code == 401
    provider.assert_not_called()
    execute.assert_not_called()


@pytest.mark.parametrize("extra", [
    {"send_enabled": True}, {"governed_enabled": True},
    {"actor_user_id": 99}, {"retry": True},
    {"provider_channel_id": "another-channel"},
])
def test_browser_cannot_override_gates_or_identity(api, extra):
    browser, headers = api
    browser.application.config.update(
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=True,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=True,
    )
    with patch.object(routes, "_resolve_request_access",
                      return_value=(SimpleNamespace(id=47), access())), \
         patch.object(routes, "IVentasBroadcastProvider") as provider, \
         patch.object(routes, "execute_governed_child") as execute:
        response = browser.post(ENDPOINT, headers=headers, json={**GOOD, **extra})
    assert response.status_code == 400
    provider.assert_not_called()
    execute.assert_not_called()


@pytest.mark.parametrize("outcome,expected_http", [
    ("SUBMITTED", 200),
    ("RECONCILIATION_REQUIRED", 502),
    ("PROVIDER_ERROR", 502),
])
def test_enabled_gates_call_exactly_one_mocked_service_not_real_iventas(
    api, outcome, expected_http,
):
    browser, headers = api
    browser.application.config.update(
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=True,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=True,
    )
    with patch.object(routes, "_resolve_request_access",
                      return_value=(SimpleNamespace(id=47), access())), \
         patch.object(routes, "IVentasBroadcastProvider") as provider, \
         patch.object(routes, "execute_governed_child", return_value={
             "status": outcome, "child_id": 100,
             "execution_status": "REVIEW_REQUIRED" if outcome != "SUBMITTED" else "COMPLETE",
         }) as execute:
        response = browser.post(ENDPOINT, headers=headers, json=GOOD)
    assert response.status_code == expected_http
    assert execute.call_count == 1
    assert execute.call_args.kwargs["actor_user_id"] == 47
    assert execute.call_args.kwargs["child_id"] == 100
    assert execute.call_args.kwargs["expected_digest"] == GOOD["expected_manifest_digest"]
    assert execute.call_args.kwargs["send_enabled"] is True
    assert execute.call_args.kwargs["governed_enabled"] is True
    assert execute.call_args.kwargs["provider"] is provider.return_value
    # Instantiating a fake provider is not an actual network call.
    provider.return_value.create_campaign.assert_not_called()


def test_not_authorize_not_materialize_and_monitor_are_never_provider_writes(api):
    browser, headers = api
    with patch.object(routes, "_resolve_request_access",
                      return_value=(SimpleNamespace(id=47), access())), \
         patch.object(routes, "IVentasBroadcastProvider") as provider, \
         patch.object(routes, "get_dispatch_approval", return_value={
             "approval": None, "send_authorized": False,
         }), \
         patch.object(routes, "review_execution", return_value={
             "approval": None, "execution": None, "send_authorized": False,
         }), \
         patch.object(routes, "read_governed_dispatch_monitor", return_value={
             "children": [], "may_auto_retry": False,
             "may_auto_release_held": False, "send_authorized": False,
         }):
        for path in ("approval", "execution", "monitor"):
            response = browser.get(
                f"/api/marketing/campaigns-v2/99/dispatch/{path}", headers=headers,
            )
            assert response.status_code == 200
    provider.assert_not_called()
