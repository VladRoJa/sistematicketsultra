"""HTTP gates for mass evidence: exact actor, no provider send."""
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes
from app.services import marketing_campaign_v2_bulk_template_evidence_service as bulk

BASE = "/api/marketing/campaigns-v2/dispatch/templates/12/inventory/"
BODY = {"inventory": [{"name": "promos_noviembre_v", "status": "accepted",
        "channelId": "c1", "channel": {"id": "c1", "name": "Ultra"}}]}
CAPABILITIES = dict(is_global=True, can_manage_dispatch_config=True,
                    can_send_campaigns=True)


def client():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-bulk-inventory-only")
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("path", ["preview", "register"])
def test_jwt_and_global_gates(path):
    api, headers = client()
    assert api.post(BASE + path, json=BODY).status_code == 401
    for key in CAPABILITIES:
        access = NS(**(CAPABILITIES | {key: False}))
        with patch.object(routes, "_resolve_request_access", return_value=(NS(id=47), access)), \
             patch.object(bulk, "preview_bulk_template_inventory") as preview, \
             patch.object(bulk, "register_bulk_template_inventory") as register:
            response = api.post(BASE + path, headers=headers, json=BODY)
        assert response.status_code == 403
        preview.assert_not_called()
        register.assert_not_called()


def test_preview_is_not_a_send_and_cannot_select_provider_channels():
    api, headers = client()
    with patch.object(routes, "_resolve_request_access",
                      return_value=(NS(id=47), NS(**CAPABILITIES))), \
         patch.object(bulk, "preview_bulk_template_inventory",
                      return_value={"rows": [], "provider_requests": 0}) as preview:
        response = api.post(BASE + "preview", headers=headers, json=BODY)
        assert response.status_code == 200
        assert response.json["provider_requests"] == 0
        assert preview.call_args.kwargs["template_id"] == 12
        invalid = api.post(BASE + "preview", headers=headers,
                           json=BODY | {"provider_channel_id": "injected"})
        assert invalid.status_code == 400


def test_register_gets_actor_from_jwt_and_no_dispatch_instruction():
    api, headers = client()
    payload = BODY | {"observed_at": "2026-11-09T16:00:00-08:00",
                      "source_reference": "iVentas provider inventory captured",
                      "expected_fingerprint": "a" * 64,
                      "confirmed_provider_capture": True}
    with patch.object(routes, "_resolve_request_access",
                      return_value=(NS(id=47), NS(**CAPABILITIES))), \
         patch.object(bulk, "register_bulk_template_inventory",
                      return_value={"recorded": 2, "send_authorized": False}) as register:
        response = api.post(BASE + "register", headers=headers, json=payload)
        assert response.status_code == 201
        assert response.json["send_authorized"] is False
        assert register.call_args.kwargs["actor_user_id"] == 47
        bad = api.post(BASE + "register", headers=headers,
                       json=payload | {"send": True})
        assert bad.status_code == 400
        assert register.call_count == 1
