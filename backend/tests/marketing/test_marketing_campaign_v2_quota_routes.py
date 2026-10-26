"""Issue #856 D1: quota admin route permission and provider independence."""
from importlib.metadata import version
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

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


@pytest.mark.parametrize(
    "operation,service_name,payload",
    [
        pytest.param(
            "approval", "approve_dispatch_reservation",
            {
                "template_id": 2,
                "expected_dispatch_fingerprint": "a" * 64,
                "expected_quote_fingerprint": "b" * 64,
                "expected_recipients": 12,
                "expected_total_mxn": "3.60",
            },
            id="approval",
        ),
        pytest.param(
            "authorize", "authorize_governed_dispatch",
            {
                "approval_id": 9,
                "expected_manifest_digest": "a" * 64,
                "expected_ready_recipients": 5,
                "confirm_dispatch": True,
            },
            id="authorize",
        ),
    ],
)
@pytest.mark.parametrize(
    "denied_capability",
    ["non_global", "missing_send", "missing_dispatch_config"],
)
def test_dispatch_approval_and_authorize_deny_before_side_effects(
    client, global_access, operation, service_name, payload, denied_capability,
):
    """P26.2: nunca alcanza la escritura ni el proveedor ante falta de acceso.

    JWT real y capacidades sinteticas. No consulta PostgreSQL ni ejecuta
    operaciones de campañas: los servicios y la sesion DB son mocks.
    """
    browser, headers = client
    access = SimpleNamespace(**vars(global_access))
    if denied_capability == "non_global":
        access.is_global = False
        access.branch_ids = (11,)
    elif denied_capability == "missing_send":
        access.can_send_campaigns = False
    else:
        access.can_manage_dispatch_config = False

    endpoint = f"/api/marketing/campaigns-v2/99/dispatch/{operation}"
    with auth(access), patch.object(
        routes, service_name,
    ) as mutation, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "_parse_payload",
    ) as parse_payload, patch.object(
        routes, "_campaign_v2_allowed_sucursal_keys",
    ) as branch_keys, patch.object(
        routes, "db",
    ) as fake_db:
        response = browser.post(endpoint, json=payload, headers=headers)

    assert response.status_code == 403, (operation, denied_capability, response.json)
    assert response.json["status"] == "error"
    mutation.assert_not_called()
    provider.assert_not_called()
    parse_payload.assert_not_called()
    branch_keys.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.delete.assert_not_called()
    fake_db.session.flush.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()


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





@pytest.mark.parametrize(
    "operation,service_name,payload",
    [
        pytest.param(
            "reauthorize", "reauthorize_unattempted_dispatch",
            {
                "previous_approval_id": 9,
                "expected_manifest_digest": "a" * 64,
                "confirmation": "REAUTORIZAR 99",
            },
            id="reauthorize",
        ),
        pytest.param(
            "materialize", "materialize_approved_manifest",
            {},
            id="materialize",
        ),
    ],
)
@pytest.mark.parametrize(
    "denied_capability",
    ["non_global", "missing_send", "missing_dispatch_config"],
)
def test_reauthorize_and_materialize_deny_before_side_effects(
    client, global_access, operation, service_name, payload, denied_capability,
):
    """P26.3: el guard corta antes de servicio y persistencia simulada.

    JWT Flask real, acceso sintetico y sin conexion a datos de produccion.
    """
    browser, headers = client
    access = SimpleNamespace(**vars(global_access))
    if denied_capability == "non_global":
        access.is_global = False
        access.branch_ids = (11,)
    elif denied_capability == "missing_send":
        access.can_send_campaigns = False
    else:
        access.can_manage_dispatch_config = False

    with auth(access), patch.object(
        routes, service_name,
    ) as mutation, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "_parse_payload",
    ) as parse_payload, patch.object(
        routes, "_campaign_v2_allowed_sucursal_keys",
    ) as branch_keys, patch.object(
        routes, "db",
    ) as fake_db:
        response = browser.post(
            f"/api/marketing/campaigns-v2/99/dispatch/{operation}",
            json=payload,
            headers=headers,
        )

    assert response.status_code == 403, (operation, denied_capability, response.json)
    assert response.json["status"] == "error"
    mutation.assert_not_called()
    provider.assert_not_called()
    parse_payload.assert_not_called()
    branch_keys.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.delete.assert_not_called()
    fake_db.session.flush.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()


def test_reauthorize_requires_explicit_campaign_bound_confirmation(
    client, global_access,
):
    """P26.3: un texto que confirma otra campaña no permite reautorizar."""
    browser, headers = client
    with auth(global_access), patch.object(
        routes, "reauthorize_unattempted_dispatch",
    ) as reauthorize, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "_campaign_v2_allowed_sucursal_keys",
    ) as branch_keys, patch.object(
        routes, "db",
    ) as fake_db:
        response = browser.post(
            "/api/marketing/campaigns-v2/99/dispatch/reauthorize",
            json={
                "previous_approval_id": 9,
                "expected_manifest_digest": "a" * 64,
                "confirmation": "REAUTORIZAR 100",
            },
            headers=headers,
        )

    assert response.status_code == 400
    assert "Confirmación explícita" in response.json["message"]
    reauthorize.assert_not_called()
    provider.assert_not_called()
    branch_keys.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()


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



def test_dispatch_execute_wrong_password_blocks_before_provider_and_claim(
    client,
):
    """P26: clave incorrecta rechaza antes de proveedor o claim de DB.

    JWT real, identidad/rol sinteticos y banderas habilitadas SOLO en el
    Flask app de esta prueba. No conecta servicios externos ni ejecuta envios.
    """
    browser, headers = client
    browser.application.config.update(
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=True,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=True,
    )
    verify_password = Mock(return_value=False)
    actor = SimpleNamespace(
        id=7,
        username="MARKETING_QA",
        rol="MARKETING",
        verify_password=verify_password,
    )
    payload = {
        "execution_id": 41,
        "child_id": 100,
        "expected_manifest_digest": "a" * 64,
        "operator_password": "clave-ficticia-incorrecta",
    }

    with patch.object(
        routes.UserORM, "get_by_id", return_value=actor,
    ) as load_actor, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "execute_governed_child",
    ) as dispatch:
        response = browser.post(
            "/api/marketing/campaigns-v2/99/dispatch/execute",
            json=payload, headers=headers,
        )

    assert response.status_code == 403
    assert "Contraseña" in response.get_json()["message"]
    load_actor.assert_called_once_with(7)
    verify_password.assert_called_once_with("clave-ficticia-incorrecta")
    provider.assert_not_called()
    dispatch.assert_not_called()


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


@pytest.mark.parametrize(
    "operation,service_name,payload",
    [
        pytest.param(
            "escalate", "escalate_stale_governed_claim",
            {
                "child_id": 100,
                "expected_manifest_digest": "a" * 64,
                "source_reference": "synthetic evidence",
                "evidence_note": "Manual investigation requested.",
            },
            id="escalate",
        ),
        pytest.param(
            "resolve", "record_governed_provider_resolution",
            {
                "child_id": 100,
                "expected_manifest_digest": "a" * 64,
                "resolution": "PROVIDER_CAMPAIGN_FOUND",
                "provider_campaign_id": "synthetic-id",
                "source_reference": "synthetic evidence",
                "evidence_note": "Manually verified outcome.",
            },
            id="resolve",
        ),
    ],
)
@pytest.mark.parametrize(
    "denied_capability",
    ["non_global", "missing_send", "missing_dispatch_config"],
)
def test_escalate_and_resolve_deny_before_side_effects(
    client, global_access, operation, service_name, payload, denied_capability,
):
    """P26.4: guards deniegan antes de parser, servicio y DB simulada.

    Las rutas usan JWT Flask en entorno de prueba y acceso sintetico.
    No hay ejecucion de envios ni conexion a datos de produccion.
    """
    browser, headers = client
    access = SimpleNamespace(**vars(global_access))
    if denied_capability == "non_global":
        access.is_global = False
        access.branch_ids = (11,)
    elif denied_capability == "missing_send":
        access.can_send_campaigns = False
    else:
        access.can_manage_dispatch_config = False

    with auth(access), patch.object(
        routes, service_name,
    ) as mutation, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "_parse_payload",
    ) as parse_payload, patch.object(
        routes, "_campaign_v2_allowed_sucursal_keys",
    ) as branch_keys, patch.object(
        routes, "db",
    ) as fake_db:
        response = browser.post(
            f"/api/marketing/campaigns-v2/77/dispatch/executions/41/{operation}",
            json=payload,
            headers=headers,
        )

    assert response.status_code == 403, (operation, denied_capability, response.json)
    assert response.json["status"] == "error"
    mutation.assert_not_called()
    provider.assert_not_called()
    parse_payload.assert_not_called()
    branch_keys.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.delete.assert_not_called()
    fake_db.session.flush.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()


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


@pytest.mark.parametrize(
    "operation,service_name,payload",
    [
        pytest.param(
            "release-intent", "request_held_release_intent",
            {
                "expected_candidate_fingerprint": "a" * 64,
                "expected_recipient_count": 5,
                "source_reference": "synthetic quota evidence",
                "reason": "fresh capacity",
            },
            id="release-intent",
        ),
        pytest.param(
            "freeze-derived", "freeze_derived_held_cohort",
            {
                "intent_id": 55,
                "expected_candidate_fingerprint": "a" * 64,
                "expected_recipient_count": 5,
            },
            id="freeze-derived",
        ),
    ],
)
@pytest.mark.parametrize(
    "denied_capability",
    ["non_global", "missing_send", "missing_dispatch_config"],
)
def test_held_release_intent_and_freeze_derived_deny_before_side_effects(
    client, global_access, operation, service_name, payload, denied_capability,
):
    """P26.5: guard 403 antes de servicios HELD o persistencia simulada.

    JWT de Flask real y accesos sinteticos; sin proveedor ni datos reales.
    """
    browser, headers = client
    access = SimpleNamespace(**vars(global_access))
    if denied_capability == "non_global":
        access.is_global = False
        access.branch_ids = (11,)
    elif denied_capability == "missing_send":
        access.can_send_campaigns = False
    else:
        access.can_manage_dispatch_config = False

    with auth(access), patch.object(
        routes, service_name,
    ) as mutation, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "_parse_payload",
    ) as parse_payload, patch.object(
        routes, "_campaign_v2_allowed_sucursal_keys",
    ) as branch_keys, patch.object(
        routes, "db",
    ) as fake_db:
        response = browser.post(
            f"/api/marketing/campaigns-v2/77/dispatch/held/100/{operation}",
            json=payload,
            headers=headers,
        )

    assert response.status_code == 403, (operation, denied_capability, response.json)
    assert response.json["status"] == "error"
    mutation.assert_not_called()
    provider.assert_not_called()
    parse_payload.assert_not_called()
    branch_keys.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.delete.assert_not_called()
    fake_db.session.flush.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()


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


@pytest.mark.parametrize(
    "operation,service_name,payload,denied_reason",
    [
        pytest.param(
            "create", "freeze_campaign_v2",
            {
                "name": "Synthetic creation",
                "purpose": "ACTIVE_MEMBERS",
                "source": "ACTIVE_MEMBERS",
                "audience_families": ["DOMICILIADO"],
                "expected_preview_fingerprint": "a" * 64,
            },
            "missing_management",
            id="create-no-management",
        ),
        pytest.param(
            "create", "freeze_campaign_v2",
            {
                "name": "Synthetic creation",
                "purpose": "ACTIVE_MEMBERS",
                "source": "ACTIVE_MEMBERS",
                "audience_families": ["DOMICILIADO"],
                "expected_preview_fingerprint": "a" * 64,
            },
            "empty_branch_scope",
            id="create-empty-branch-scope",
        ),
        pytest.param(
            "followup", "freeze_followup_campaign",
            {
                "name": "Synthetic followup",
                "selected_statuses": ["VIEWED"],
                "source_snapshot_id": 101,
                "expected_preview_fingerprint": "b" * 64,
                "expected_recipient_count": 3,
            },
            "empty_branch_scope",
            id="followup-empty-branch-scope",
        ),
    ],
)
def test_campaign_freeze_rejects_unmanaged_or_empty_branch_scope(
    client, partial_access, operation, service_name, payload, denied_reason,
):
    """P26.6: sin gestión o sucursales válidas no inicia una escritura."""
    browser, headers = client
    access = SimpleNamespace(**vars(partial_access))
    if denied_reason == "missing_management":
        access.can_manage_campaigns = False

    url = (
        "/api/marketing/campaigns-v2"
        if operation == "create"
        else "/api/marketing/campaigns-v2/77/followup/freeze"
    )
    with auth(access), patch.object(
        routes, service_name,
    ) as mutation, patch.object(
        routes, "marketing_branch_keys_by_sucursal_ids",
        return_value={},
    ) as branch_mapper, patch.object(
        routes, "_parse_payload", wraps=routes._parse_payload,
    ) as parse_payload, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "db",
    ) as fake_db:
        response = browser.post(url, json=payload, headers=headers)

    assert response.status_code == 403, (operation, denied_reason, response.json)
    assert response.json["status"] == "error"
    mutation.assert_not_called()
    provider.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.delete.assert_not_called()
    fake_db.session.flush.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()
    if denied_reason == "missing_management":
        parse_payload.assert_not_called()
        branch_mapper.assert_not_called()
        assert "gestionar" in response.json["message"]
    else:
        parse_payload.assert_called_once()
        branch_mapper.assert_called_once()
        assert branch_mapper.call_args.kwargs["sucursal_ids"] == access.branch_ids
        assert "sucursales" in response.json["message"]


def test_campaign_create_preserves_authorized_partial_branch_scope(
    client, partial_access,
):
    """P26.6: crear con alcance parcial no exige permiso de envío/global."""
    browser, headers = client
    assert partial_access.is_global is False
    assert partial_access.can_manage_campaigns is True
    assert partial_access.can_send_campaigns is False
    payload = {
        "name": "Synthetic scoped campaign",
        "purpose": "ACTIVE_MEMBERS",
        "source": "ACTIVE_MEMBERS",
        "audience_families": ["DOMICILIADO"],
        "expected_preview_fingerprint": "c" * 64,
    }
    with auth(partial_access), patch.object(
        routes, "marketing_branch_keys_by_sucursal_ids",
        return_value={11: "BRANCH A"},
    ) as branch_mapper, patch.object(
        routes, "freeze_campaign_v2",
        return_value={"campaign_id": 99, "recipient_count": 1},
    ) as freeze, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider:
        response = browser.post(
            "/api/marketing/campaigns-v2",
            json=payload, headers=headers,
        )

    assert response.status_code == 201
    branch_mapper.assert_called_once()
    assert branch_mapper.call_args.kwargs["sucursal_ids"] == partial_access.branch_ids
    freeze.assert_called_once()
    assert freeze.call_args.kwargs["created_by_user_id"] == 7
    assert freeze.call_args.kwargs["allowed_sucursal_keys"] == ("BRANCH A",)
    assert freeze.call_args.kwargs["marketing_access"] is partial_access
    provider.assert_not_called()


@pytest.mark.parametrize(
    "denied_reason",
    ["missing_management", "empty_branch_scope"],
)
def test_excel_freeze_denies_before_service(
    client, partial_access, denied_reason,
):
    """P26.7: la importacion Excel no esquiva gestion ni alcance regional."""
    browser, headers = client
    access = SimpleNamespace(**vars(partial_access))
    if denied_reason == "missing_management":
        access.can_manage_campaigns = False
    data = {
        "name": "Synthetic Excel campaign",
        "purpose": "ACTIVE_MEMBERS",
        "template_id": "2",
        "expected_preview_fingerprint": "a" * 64,
        "file": (BytesIO(b"phone_mx10,sucursal\n6861234567,BRANCH A\n"), "synthetic.csv"),
    }
    with auth(access), patch.object(
        routes, "freeze_excel_campaign",
    ) as freeze, patch.object(
        routes, "marketing_branch_keys_by_sucursal_ids", return_value={},
    ) as mapper, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "db",
    ) as fake_db:
        response = browser.post(
            "/api/marketing/campaigns-v2/excel/freeze",
            data=data, content_type="multipart/form-data", headers=headers,
        )

    assert response.status_code == 403, (denied_reason, response.json)
    assert response.json["status"] == "error"
    freeze.assert_not_called()
    provider.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.delete.assert_not_called()
    fake_db.session.flush.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()
    if denied_reason == "missing_management":
        mapper.assert_not_called()
        assert "gestionar" in response.json["message"]
    else:
        mapper.assert_called_once()
        assert mapper.call_args.kwargs["sucursal_ids"] == partial_access.branch_ids
        assert "sucursales" in response.json["message"]


def test_excel_freeze_preserves_authorized_partial_scope_without_send(
    client, partial_access,
):
    """P26.7: el Excel solo congela sucursales autorizadas y nunca envia."""
    browser, headers = client
    assert partial_access.is_global is False
    assert partial_access.can_manage_campaigns is True
    assert partial_access.can_send_campaigns is False
    file_bytes = b"phone_mx10,sucursal\n6861234567,BRANCH A\n"
    data = {
        "name": "Synthetic Excel campaign",
        "purpose": "ACTIVE_MEMBERS",
        "template_id": "2",
        "expected_preview_fingerprint": "b" * 64,
        "file": (BytesIO(file_bytes), "synthetic.csv"),
    }
    with auth(partial_access), patch.object(
        routes, "marketing_branch_keys_by_sucursal_ids",
        return_value={11: "BRANCH A"},
    ) as mapper, patch.object(
        routes, "freeze_excel_campaign",
        return_value={"campaign_id": 99, "recipient_count": 1},
    ) as freeze, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "db",
    ) as fake_db:
        response = browser.post(
            "/api/marketing/campaigns-v2/excel/freeze",
            data=data, content_type="multipart/form-data", headers=headers,
        )

    assert response.status_code == 201
    mapper.assert_called_once()
    assert mapper.call_args.kwargs["sucursal_ids"] == partial_access.branch_ids
    freeze.assert_called_once()
    kwargs = freeze.call_args.kwargs
    assert kwargs["created_by_user_id"] == 7
    assert kwargs["file_bytes"] == file_bytes
    assert kwargs["filename"] == "synthetic.csv"
    assert kwargs["template_id"] == 2
    assert kwargs["expected_preview_fingerprint"] == "b" * 64
    assert kwargs["allowed_sucursal_keys"] == ("BRANCH A",)
    assert kwargs["session"] is fake_db.session
    provider.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.commit.assert_not_called()


@pytest.mark.parametrize(
    "method,path_suffix,service_name,payload",
    [
        pytest.param(
            "patch", "purpose", "update_campaign_v2_purpose",
            {"purpose": "NEW_SALE"},
            id="purpose",
        ),
        pytest.param(
            "put", "provider-binding", "bind_campaign_v2_provider",
            {"provider": "IVENTAS", "provider_campaign_id": "synthetic-123"},
            id="provider-binding",
        ),
    ],
)
@pytest.mark.parametrize(
    "denied_reason",
    ["missing_management", "empty_branch_scope"],
)
def test_campaign_metadata_mutations_deny_before_service(
    client, partial_access, method, path_suffix, service_name, payload,
    denied_reason,
):
    """P26.8: falta de gestion o alcance vacio bloquea cambios de metadata."""
    browser, headers = client
    access = SimpleNamespace(**vars(partial_access))
    if denied_reason == "missing_management":
        access.can_manage_campaigns = False

    with auth(access), patch.object(
        routes, service_name,
    ) as mutation, patch.object(
        routes, "marketing_branch_keys_by_sucursal_ids", return_value={},
    ) as mapper, patch.object(
        routes, "_parse_payload", wraps=routes._parse_payload,
    ) as parse_payload, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "db",
    ) as fake_db:
        response = getattr(browser, method)(
            f"/api/marketing/campaigns-v2/77/{path_suffix}",
            json=payload, headers=headers,
        )

    assert response.status_code == 403, (path_suffix, denied_reason, response.json)
    assert response.json["status"] == "error"
    mutation.assert_not_called()
    provider.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.delete.assert_not_called()
    fake_db.session.flush.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()

    if denied_reason == "missing_management":
        parse_payload.assert_not_called()
        mapper.assert_not_called()
        assert "gestionar" in response.json["message"]
    else:
        parse_payload.assert_called_once()
        mapper.assert_called_once()
        assert mapper.call_args.kwargs["sucursal_ids"] == partial_access.branch_ids
        assert "sucursales" in response.json["message"]


@pytest.mark.parametrize(
    "method,path_suffix,service_name,payload,result",
    [
        pytest.param(
            "patch", "purpose", "update_campaign_v2_purpose",
            {"purpose": "NEW_SALE"},
            {"id": 77, "purpose": "NEW_SALE"},
            id="purpose",
        ),
        pytest.param(
            "put", "provider-binding", "bind_campaign_v2_provider",
            {"provider": "IVENTAS", "provider_campaign_id": "synthetic-123"},
            {"campaign_id": 77, "provider": "IVENTAS", "created": True},
            id="provider-binding",
        ),
    ],
)
def test_campaign_metadata_mutations_preserve_partial_scope(
    client, partial_access, method, path_suffix, service_name, payload, result,
):
    """P26.8: el manager regional puede modificar solo con scope backend."""
    browser, headers = client
    assert partial_access.is_global is False
    assert partial_access.can_manage_campaigns is True
    assert partial_access.can_send_campaigns is False
    with auth(partial_access), patch.object(
        routes, "marketing_branch_keys_by_sucursal_ids",
        return_value={11: "BRANCH A"},
    ) as mapper, patch.object(
        routes, service_name, return_value=result,
    ) as mutation, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(
        routes, "db",
    ) as fake_db:
        response = getattr(browser, method)(
            f"/api/marketing/campaigns-v2/77/{path_suffix}",
            json=payload, headers=headers,
        )

    assert response.status_code == 200
    assert response.json == result
    mapper.assert_called_once()
    assert mapper.call_args.kwargs["sucursal_ids"] == partial_access.branch_ids
    mutation.assert_called_once()
    kwargs = mutation.call_args.kwargs
    assert kwargs["campaign_id"] == 77
    assert kwargs["allowed_sucursal_keys"] == ("BRANCH A",)
    assert kwargs["session"] is fake_db.session
    for key, value in payload.items():
        assert kwargs[key] == value
    provider.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.commit.assert_not_called()


@pytest.mark.parametrize(
    "method,path,service_name",
    [
        pytest.param(
            "get", "/api/marketing/campaigns-v2/77/export-package",
            "export_campaign_v2_delivery_package", id="manual-export",
        ),
        pytest.param(
            "get", "/api/marketing/campaigns-v2/77/sendable-export-package",
            "export_campaign_v2_sendable_package", id="sendable-export",
        ),
        pytest.param(
            "get", "/api/marketing/campaigns-v2/77/recipients",
            "list_campaign_v2_recipients", id="recipients-list",
        ),
        pytest.param(
            "get", "/api/marketing/campaigns-v2/77/recipients/15",
            "get_campaign_v2_recipient", id="recipient-detail",
        ),
        pytest.param(
            "post", "/api/marketing/campaigns-v2/77/provider-stats/snapshots",
            "capture_campaign_v2_provider_stats_snapshot", id="provider-stats-capture",
        ),
    ],
)
def test_p26_9_empty_regional_scope_blocks_sensitive_reads_and_capture(
    client, partial_access, method, path, service_name,
):
    """A managed account without resolved branches must fail before the service."""
    browser, headers = client
    assert partial_access.can_manage_campaigns is True
    assert partial_access.is_global is False
    with auth(partial_access), patch.object(
        routes, "marketing_branch_keys_by_sucursal_ids", return_value={},
    ) as mapper, patch.object(
        routes, service_name,
    ) as operation, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(routes, "db") as fake_db:
        response = getattr(browser, method)(path, headers=headers)

    assert response.status_code == 403, (method, path, response.json)
    mapper.assert_called_once()
    assert mapper.call_args.kwargs["sucursal_ids"] == partial_access.branch_ids
    operation.assert_not_called()
    provider.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.commit.assert_not_called()
    fake_db.session.execute.assert_not_called()


def test_p26_9_regional_stats_capture_forwards_only_authorized_branches(
    client, partial_access,
):
    """Positive HTTP handler contract; no real provider request or DB write."""
    browser, headers = client
    expected = {"id": 8, "campaign_id": 77, "created": True}
    with auth(partial_access), patch.object(
        routes, "marketing_branch_keys_by_sucursal_ids",
        return_value={11: "BRANCH A"},
    ) as mapper, patch.object(
        routes, "capture_campaign_v2_provider_stats_snapshot",
        return_value=expected,
    ) as capture, patch.object(
        routes, "IVentasBroadcastProvider",
    ) as provider, patch.object(routes, "db") as fake_db:
        response = browser.post(
            "/api/marketing/campaigns-v2/77/provider-stats/snapshots",
            headers=headers,
        )

    assert response.status_code == 200, response.json
    assert response.json == expected
    mapper.assert_called_once()
    capture.assert_called_once()
    assert capture.call_args.kwargs == {
        "campaign_id": 77,
        "allowed_sucursal_keys": ("BRANCH A",),
        "session": fake_db.session,
    }
    provider.assert_not_called()
    fake_db.session.add.assert_not_called()
    fake_db.session.commit.assert_not_called()
