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
        "expected_quote_fingerprint": "b" * 64,
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


def test_governed_materialization_requires_global_dispatch_and_send(
    client, global_access, partial_access,
):
    browser, headers = client
    endpoint = "/api/marketing/campaigns-v2/99/dispatch/materialize"
    with auth(partial_access), patch.object(routes, "materialize_approved_manifest") as m:
        response = browser.post(endpoint, json={}, headers=headers)
    assert response.status_code == 403
    m.assert_not_called()
    with auth(global_access), patch.object(
        routes, "materialize_approved_manifest",
        return_value={"status": "PREPARED_NO_SEND", "send_authorized": False},
    ) as m, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post(endpoint, json={}, headers=headers)
    assert response.status_code == 201
    assert response.json["send_authorized"] is False
    assert m.call_args.kwargs["actor_user_id"] == 7
    provider.assert_not_called()


def test_governed_materialization_rejects_provider_or_kill_switch_override(
    client, global_access,
):
    browser, headers = client
    with auth(global_access), patch.object(routes, "materialize_approved_manifest") as m:
        response = browser.post(
            "/api/marketing/campaigns-v2/99/dispatch/materialize",
            json={"send_enabled": True}, headers=headers,
        )
    assert response.status_code == 400
    m.assert_not_called()


def test_dispatch_execution_requires_global_permissions_and_both_switches(
    client, global_access, partial_access,
):
    browser, headers = client
    url = "/api/marketing/campaigns-v2/99/dispatch/execute"
    payload = {
        "execution_id": 41, "child_id": 100,
        "expected_manifest_digest": "a"*64,
    }
    with auth(partial_access), patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post(url, json=payload, headers=headers)
    assert response.status_code == 403
    provider.assert_not_called()

    with auth(global_access), patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post(url, json=payload, headers=headers)
    assert response.status_code == 423
    provider.assert_not_called()

    # Existing send flag alone must never enable new governed dispatch.
    with auth(global_access), patch.object(routes, "IVentasBroadcastProvider") as provider:
        browser.application.config["CAMPAIGN_V2_PROVIDER_SEND_ENABLED"] = True
        response = browser.post(url, json=payload, headers=headers)
    assert response.status_code == 423
    provider.assert_not_called()


def test_dispatch_authorize_is_independent_and_does_not_instantiate_provider(
    client, global_access,
):
    browser, headers = client
    url = "/api/marketing/campaigns-v2/99/dispatch/authorize"
    payload = {
        "approval_id": 9, "expected_manifest_digest": "a"*64,
        "expected_ready_recipients": 5, "confirm_dispatch": True,
    }
    with auth(global_access), patch.object(
        routes, "authorize_governed_dispatch",
        return_value={"execution_id":41,"status":"AUTHORIZED","provider_calls":0},
    ) as authorize, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post(url, json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json["provider_calls"] == 0
    authorize.assert_called_once()
    provider.assert_not_called()


def test_dispatch_execute_rejects_extra_send_enabled_from_browser(
    client, global_access,
):
    browser, headers = client
    with auth(global_access), patch.object(routes, "execute_governed_child") as dispatch:
        response = browser.post(
            "/api/marketing/campaigns-v2/99/dispatch/execute",
            json={"execution_id":41, "child_id":100,
                  "send_enabled":True, "expected_manifest_digest":"a"*64},
            headers=headers,
        )
    assert response.status_code == 400
    dispatch.assert_not_called()


def test_governed_mode_does_not_unlock_legacy_web_submit_or_retry(
    client, global_access,
):
    browser, headers = client
    browser.application.config.update(
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=True,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=True,
    )
    with auth(global_access), patch.object(routes, "IVentasBroadcastProvider") as provider:
        submit = browser.post(
            "/api/marketing/campaigns-v2/99/submit",
            json={"template_id": 2, "expected_dispatch_fingerprint": "a"*64},
            headers=headers,
        )
        retry = browser.post(
            "/api/marketing/campaigns-v2/provider-campaigns/100/retry",
            json={}, headers=headers,
        )
    assert submit.status_code == 423
    assert retry.status_code == 423
    provider.assert_not_called()


def test_d3_monitor_is_global_read_only_no_provider(
    client, global_access, partial_access,
):
    browser, headers = client
    url = "/api/marketing/campaigns-v2/99/dispatch/monitor"
    with auth(partial_access), patch.object(routes, "read_governed_dispatch_monitor") as monitor:
        response = browser.get(url, headers=headers)
    assert response.status_code == 403
    monitor.assert_not_called()

    no_send = SimpleNamespace(**vars(global_access))
    no_send.can_send_campaigns = False
    with auth(no_send), patch.object(routes, "read_governed_dispatch_monitor") as monitor:
        response = browser.get(url, headers=headers)
    assert response.status_code == 403
    monitor.assert_not_called()

    with auth(global_access), patch.object(
        routes, "read_governed_dispatch_monitor",
        return_value={"status": "IN_FLIGHT_STALE", "send_authorized": False},
    ) as monitor, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json["send_authorized"] is False
    monitor.assert_called_once()
    provider.assert_not_called()


def test_d3_monitor_rejects_query_override(client, global_access):
    browser, headers = client
    with auth(global_access), patch.object(routes, "read_governed_dispatch_monitor") as monitor:
        response = browser.get(
            "/api/marketing/campaigns-v2/99/dispatch/monitor?auto_retry=true",
            headers=headers,
        )
    assert response.status_code == 400
    monitor.assert_not_called()


def test_d3b_manual_escalation_is_global_and_never_calls_provider(
    client, global_access, partial_access,
):
    browser, headers = client
    endpoint = "/api/marketing/campaigns-v2/77/dispatch/executions/41/escalate"
    payload = {
        "child_id": 100, "expected_manifest_digest": "a"*64,
        "source_reference": "synthetic provider evidence",
        "evidence_note": "Verificado manualmente sin confirmar resultado.",
    }
    with auth(partial_access), patch.object(routes, "escalate_stale_governed_claim") as op:
        response = browser.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 403
    op.assert_not_called()

    with auth(global_access), patch.object(
        routes, "escalate_stale_governed_claim",
        return_value={"execution_status":"REVIEW_REQUIRED","provider_outcome":"UNKNOWN",
                      "send_authorized":False},
    ) as op, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json["send_authorized"] is False
    assert op.call_args.kwargs["campaign_id"] == 77
    provider.assert_not_called()


def test_d3b_resolution_rejects_extra_send_override(
    client, global_access,
):
    browser, headers = client
    endpoint = "/api/marketing/campaigns-v2/77/dispatch/executions/41/resolve"
    with auth(global_access), patch.object(routes, "record_governed_provider_resolution") as op:
        response = browser.post(endpoint, json={
            "child_id": 100, "send_enabled": True,
            "expected_manifest_digest": "a"*64,
            "resolution": "NOT_CREATED_CONFIRMED",
            "source_reference": "synthetic", "evidence_note": "confirmed",
        }, headers=headers)
    assert response.status_code == 400
    op.assert_not_called()


def test_d3b_resolution_never_calls_provider(client, global_access):
    browser, headers = client
    endpoint = "/api/marketing/campaigns-v2/77/dispatch/executions/41/resolve"
    payload = {
        "child_id":100,"expected_manifest_digest":"a"*64,
        "resolution":"PROVIDER_CAMPAIGN_FOUND",
        "provider_campaign_id":"synthetic-id",
        "source_reference":"synthetic", "evidence_note":"verified",
    }
    with auth(global_access), patch.object(
        routes, "record_governed_provider_resolution",
        return_value={"execution_status":"REVIEW_REQUIRED","send_authorized":False},
    ) as op, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json["send_authorized"] is False
    op.assert_called_once()
    provider.assert_not_called()


def test_d3c_held_release_preview_global_only_no_provider(client, global_access, partial_access):
    browser, headers = client
    url = "/api/marketing/campaigns-v2/77/dispatch/held/100/release-preview"
    with auth(partial_access), patch.object(routes, "preview_held_release") as preview:
        denied = browser.get(url, headers=headers)
    assert denied.status_code == 403
    preview.assert_not_called()

    with auth(global_access), patch.object(
        routes, "preview_held_release",
        return_value={"status":"ELIGIBLE_FOR_INTENT_ONLY","send_authorized":False},
    ) as preview, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json["send_authorized"] is False
    preview.assert_called_once()
    provider.assert_not_called()


def test_d3c_held_release_intent_cannot_override_send_or_unhold(client, global_access):
    browser, headers = client
    url = "/api/marketing/campaigns-v2/77/dispatch/held/100/release-intent"
    payload = {"expected_candidate_fingerprint":"a"*64,
               "expected_recipient_count":5, "source_reference":"manual quota",
               "reason":"new window",
               "send_enabled":True}
    with auth(global_access), patch.object(routes, "request_held_release_intent") as intent:
        response = browser.post(url, json=payload, headers=headers)
    assert response.status_code == 400
    intent.assert_not_called()
    payload.pop("send_enabled")
    with auth(global_access), patch.object(
        routes, "request_held_release_intent",
        return_value={"intent_id":555,"status":"PENDING_FRESH_COHORT",
                      "send_authorized":False,"held_released":False},
    ) as intent, patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = browser.post(url, json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json["held_released"] is False
    intent.assert_called_once()
    provider.assert_not_called()


def test_d3c2_freeze_requires_global_authority_and_refuses_send_override(
    client, global_access, partial_access,
):
    browser, headers = client
    url = "/api/marketing/campaigns-v2/77/dispatch/held/100/freeze-derived"
    body = {"intent_id":55, "expected_candidate_fingerprint":"a"*64,
            "expected_recipient_count":5}
    with auth(partial_access), patch.object(routes, "freeze_derived_held_cohort") as freeze:
        denied = browser.post(url, json=body, headers=headers)
    assert denied.status_code == 403
    freeze.assert_not_called()

    with auth(global_access), patch.object(routes, "freeze_derived_held_cohort") as freeze:
        denied = browser.post(url, json={**body,"send_enabled":True}, headers=headers)
    assert denied.status_code == 400
    freeze.assert_not_called()

    with auth(global_access), patch.object(
        routes, "freeze_derived_held_cohort",
        return_value={"derived_campaign_id":999, "status":"FROZEN_DERIVED",
                      "provider_calls":0, "send_authorized":False},
    ) as freeze, patch.object(routes, "IVentasBroadcastProvider") as provider:
        result = browser.post(url, json=body, headers=headers)
    assert result.status_code == 201
    assert result.json["send_authorized"] is False
    freeze.assert_called_once()
    provider.assert_not_called()
