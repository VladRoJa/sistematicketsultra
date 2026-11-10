from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes
from app.services import marketing_campaign_v2_template_probe_service as probe

URL = "/api/marketing/campaigns-v2/42/dispatch/template-probes"
BODY = dict(template_id=7, selected_channel_ids=["tec"], recipient_name="QA", phone="6861000001",
            authorization_reference="Autorizado para QA", confirmed_authorized=True)
GATES = dict(is_global=True, can_manage_dispatch_config=True, can_manage_campaigns=True,
             can_preflight_campaigns=True, can_send_campaigns=True)


def client():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-template-probe-jwt-tests-only")
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_requires_jwt(method):
    api, _ = client()
    assert api.open(URL, method=method, json=BODY).status_code == 401


@pytest.mark.parametrize("gate", list(GATES))
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_requires_every_global_capability_before_service(method, gate):
    api, headers = client()
    access = NS(**(GATES | {gate: False}))
    with patch.object(routes, "_resolve_request_access", return_value=(NS(id=47), access)), \
         patch.object(probe, "prepare_template_probes") as prepare, \
         patch.object(probe, "template_probe_matrix") as matrix:
        result = api.open(URL + "?template_id=7", method=method, headers=headers, json=BODY)
    assert result.status_code == 403
    prepare.assert_not_called()
    matrix.assert_not_called()


def test_prepare_uses_jwt_actor_and_never_dispatches():
    api, headers = client()
    with patch.object(routes, "_resolve_request_access", return_value=(NS(id=47), NS(**GATES))), \
         patch.object(probe, "prepare_template_probes", return_value={"sends_started": False}) as prepare:
        response = api.post(URL, headers=headers, json=BODY)
    assert response.status_code == 200
    assert prepare.call_args.kwargs["actor_user_id"] == 47
    assert response.json["sends_started"] is False


@pytest.mark.parametrize("extra", ["actor_user_id", "provider_channel_id", "recipients", "send"])
def test_does_not_accept_client_dispatch_targets_or_actor(extra):
    api, headers = client()
    with patch.object(routes, "_resolve_request_access", return_value=(NS(id=47), NS(**GATES))), \
         patch.object(routes.db, "session", MagicMock()), \
         patch.object(probe, "prepare_template_probes") as prepare:
        response = api.post(URL, headers=headers, json=BODY | {extra: "forbidden"})
    assert response.status_code == 400
    prepare.assert_not_called()


def test_matrix_is_read_only_and_explicit_template():
    api, headers = client()
    with patch.object(routes, "_resolve_request_access", return_value=(NS(id=47), NS(**GATES))), \
         patch.object(probe, "template_probe_matrix", return_value={"rows": []}) as matrix, \
         patch.object(probe, "prepare_template_probes") as prepare:
        response = api.get(URL + "?template_id=7", headers=headers)
    assert response.status_code == 200
    assert matrix.call_args.kwargs["template_id"] == 7
    prepare.assert_not_called()


CATALOG_URL = "/api/marketing/campaigns-v2/dispatch/template-certifications/7"


def test_catalog_certification_requires_jwt_and_all_global_gates():
    api, headers = client()
    assert api.get(CATALOG_URL).status_code == 401
    assert api.post(CATALOG_URL, json={
        "recipient_name": "QA", "phone": "6861000001",
        "authorization_reference": "QA autorizada",
        "confirmed_authorized": True,
    }).status_code == 401
    for gate in GATES:
        access = NS(**(GATES | {gate: False}))
        with patch.object(routes, "_resolve_request_access",
                          return_value=(NS(id=47), access)), \
             patch.object(probe, "prepare_template_probes") as prepare, \
             patch.object(probe, "template_probe_matrix") as matrix:
            result = api.get(CATALOG_URL, headers=headers)
            assert result.status_code == 403
            prepare.assert_not_called()
            matrix.assert_not_called()


def test_catalog_endpoint_scope_does_not_require_commercial_campaign_and_never_dispatches():
    api, headers = client()
    body = dict(recipient_name="QA", selected_channel_ids=["tec"], phone="6861000001",
                authorization_reference="QA autorizada", confirmed_authorized=True)
    with patch.object(routes, "_resolve_request_access",
                      return_value=(NS(id=47), NS(**GATES))), \
         patch.object(probe, "template_probe_matrix", return_value={
             "template_id": 7, "rows": [],
         }) as matrix, \
         patch.object(probe, "prepare_template_probes", return_value={
             "template_id": 7, "rows": [], "sends_started": False,
         }) as prepare:
        read = api.get(CATALOG_URL, headers=headers)
        write = api.post(CATALOG_URL, headers=headers, json=body)
    assert read.status_code == 200
    assert write.status_code == 200
    assert matrix.call_args.kwargs["campaign_id"] is None
    assert prepare.call_args.kwargs["campaign_id"] is None
    assert prepare.call_args.kwargs["actor_user_id"] == 47
    assert write.json["sends_started"] is False


def test_catalog_rejects_client_actor_and_targets():
    api, headers = client()
    with patch.object(routes, "_resolve_request_access",
                      return_value=(NS(id=47), NS(**GATES))), \
         patch.object(probe, "prepare_template_probes") as prepare:
        result = api.post(CATALOG_URL, headers=headers, json={
            "recipient_name": "QA", "phone": "6861000001",
            "authorization_reference": "QA autorizada",
            "confirmed_authorized": True, "provider_channel_id": "other",
        })
    assert result.status_code == 400
    prepare.assert_not_called()


def test_catalog_must_require_explicit_channel_selection_before_service():
    api, headers = client()
    with patch.object(routes, "_resolve_request_access",
                      return_value=(NS(id=47), NS(**GATES))), \
         patch.object(probe, "prepare_template_probes") as prepare:
        result = api.post(CATALOG_URL, headers=headers, json={
            "recipient_name": "QA", "phone": "6861000001",
            "authorization_reference": "QA autorizada",
            "confirmed_authorized": True,
        })
    assert result.status_code == 400
    prepare.assert_not_called()


def test_catalog_passes_only_selected_channels_to_backend():
    api, headers = client()
    body = dict(recipient_name="QA", phone="6861000001",
                authorization_reference="QA autorizada", confirmed_authorized=True,
                selected_channel_ids=["villa", "cul"])
    with patch.object(routes, "_resolve_request_access",
                      return_value=(NS(id=47), NS(**GATES))), \
         patch.object(probe, "prepare_template_probes", return_value={"rows":[]}) as prepare:
        result = api.post(CATALOG_URL, headers=headers, json=body)
    assert result.status_code == 200
    assert prepare.call_args.kwargs["selected_channel_ids"] == ["villa", "cul"]


def test_campaign_must_require_explicit_channel_selection_before_service():
    api, headers = client()
    body = dict(BODY)
    body.pop("selected_channel_ids")
    with patch.object(routes, "_resolve_request_access",
                      return_value=(NS(id=47), NS(**GATES))), \
         patch.object(probe, "prepare_template_probes") as prepare:
        result = api.post(URL, headers=headers, json=body)
    assert result.status_code == 400
    prepare.assert_not_called()
