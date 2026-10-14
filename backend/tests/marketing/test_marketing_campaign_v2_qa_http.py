"""Issue 856 C — HTTP gates, exact-one QA, fingerprint and no dispatch."""
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes
from app.services import marketing_campaign_v2_qa_http_service as qa
from app.services.marketing_campaign_v2_qa_manual_service import (
    MarketingCampaignV2QAManualValidationError as QAValidation,
    MarketingCampaignV2QAManualConflictError as QAConflict,
)

BASE = {
    "name": "QA Canal Azahares 20261014",
    "purpose": "NEW_SALE",
    "sucursal_id": 16,
    "provider_channel_id": "channel-A",
    "recipients": [{"name": "Destinatario prueba", "phone": "6861000001"}],
}
BINDING = {
    "id": 12, "provider": "IVENTAS", "sucursal_id": 16,
    "provider_channel_id": "channel-A", "is_active": True, "is_default": True,
}
PREVIEW = {
    "name": BASE["name"], "purpose": "NEW_SALE", "source": "QA_MANUAL",
    "sucursal_id": 16, "sucursal_canon": "AZAHARES_CUL",
    "track_label": "AZAHARES CUL", "recipient_count": 1,
    "recipients": [{"name": "Destinatario prueba", "phone_mx10": "6861000001"}],
    "preview_fingerprint_version": "campaign-v2-qa-manual-v1",
    "preview_fingerprint": "a" * 64,
}


def fake_session(): return object()


@pytest.mark.parametrize("field,value", [
    ("name", "Campaña comercial"),
    ("recipients", []),
    ("recipients", [{"name": "a", "phone": "6861000001"}, {"name": "b", "phone": "6861000002"}]),
    ("recipients", [{"name": "a", "phone": "6861000001", "sucursal_id": 99}]),
    ("sucursal_id", True),
    ("provider_channel_id", "other-channel"),
    ("purpose", "SENDING"),
])
def test_single_channel_qa_input_strict(field, value):
    with patch.object(qa, "list_channel_bindings", return_value=[BINDING]):
        with pytest.raises(QAValidation):
            qa.preview_qa_manual_http(**{**BASE, field: value}, session=fake_session())


def test_default_binding_must_be_unique_and_active():
    with patch.object(qa, "list_channel_bindings", return_value=[BINDING, {**BINDING, "id": 13}]):
        with pytest.raises(QAValidation, match="exactamente un canal"):
            qa.preview_qa_manual_http(**BASE, session=fake_session())


def test_preview_masks_phone_and_never_writes_or_sends():
    with patch.object(qa, "list_channel_bindings", return_value=[BINDING]), \
         patch.object(qa, "build_campaign_v2_qa_manual_preview", return_value=PREVIEW) as preview, \
         patch.object(qa, "freeze_campaign_v2_qa_manual") as freeze:
        result = qa.preview_qa_manual_http(**BASE, session=fake_session())
    assert result["recipient_phone_masked"] == "******0001"
    assert "recipients" not in result and "phone_mx10" not in result
    assert result["provider_send_enabled"] is False
    assert result["is_dispatch_authorized"] is False
    assert result["preview_fingerprint"] == "a" * 64
    preview.assert_called_once()
    freeze.assert_not_called()


def test_freeze_requires_server_confirm_and_unchanged_binding_before_write():
    params = {**BASE, "expected_preview_fingerprint": "a" * 64,
              "expected_channel_binding_id": 12, "confirm_freeze": True, "actor_user_id": 47}
    with patch.object(qa, "list_channel_bindings", return_value=[BINDING]), \
         patch.object(qa, "freeze_campaign_v2_qa_manual") as freeze:
        with pytest.raises(QAValidation, match="Confirma"):
            qa.freeze_qa_manual_http(**{**params, "confirm_freeze": False}, session=fake_session())
        with pytest.raises(QAValidation, match="binding"):
            qa.freeze_qa_manual_http(**{**params, "expected_channel_binding_id": 999}, session=fake_session())
    freeze.assert_not_called()


def test_freeze_delegates_only_existing_safe_helper():
    params = {**BASE, "expected_preview_fingerprint": "a" * 64,
              "expected_channel_binding_id": 12, "confirm_freeze": True, "actor_user_id": 47}
    with patch.object(qa, "list_channel_bindings", return_value=[BINDING]), \
         patch.object(qa, "freeze_campaign_v2_qa_manual", return_value={
            "campaign_id": 16, "recipient_count": 1, "source": "QA_MANUAL",
         }) as freeze:
        result = qa.freeze_qa_manual_http(**params, session=fake_session())
    assert result["provider_send_enabled"] is False
    assert result["is_dispatch_authorized"] is False
    assert result["campaign_id"] == 16
    assert freeze.call_args.kwargs["created_by_user_id"] == 47


def client():
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = version("werkzeug")
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="test-qa-http-only")
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def full_access():
    return SimpleNamespace(
        is_global=True, can_manage_dispatch_config=True,
        can_manage_campaigns=True, can_preflight_campaigns=True,
    )


@pytest.mark.parametrize("mode", ["preview", "freeze"])
def test_qa_http_requires_jwt(mode):
    api, _ = client()
    response = api.post(f"/api/marketing/campaigns-v2/qa-manual/{mode}", json=BASE)
    assert response.status_code == 401


@pytest.mark.parametrize("access", [
    SimpleNamespace(is_global=False, can_manage_dispatch_config=True,
                    can_manage_campaigns=True, can_preflight_campaigns=True),
    SimpleNamespace(is_global=True, can_manage_dispatch_config=False,
                    can_manage_campaigns=True, can_preflight_campaigns=True),
    SimpleNamespace(is_global=True, can_manage_dispatch_config=True,
                    can_manage_campaigns=False, can_preflight_campaigns=True),
    SimpleNamespace(is_global=True, can_manage_dispatch_config=True,
                    can_manage_campaigns=True, can_preflight_campaigns=False),
])
@pytest.mark.parametrize("mode", ["preview", "freeze"])
def test_qa_http_denied_without_every_backend_gate(access, mode):
    api, headers = client()
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=47), access)), \
         patch.object(routes, "preview_qa_manual_http") as p, \
         patch.object(routes, "freeze_qa_manual_http") as f:
        response = api.post(f"/api/marketing/campaigns-v2/qa-manual/{mode}",
                            headers=headers, json=BASE)
    assert response.status_code == 403
    p.assert_not_called()
    f.assert_not_called()


def test_global_preview_does_not_write_or_forward_actor():
    api, headers = client()
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=47), full_access())), \
         patch.object(routes, "preview_qa_manual_http", return_value={"recipient_count": 1}) as preview, \
         patch.object(routes, "freeze_qa_manual_http") as freeze:
        response = api.post("/api/marketing/campaigns-v2/qa-manual/preview",
                            headers=headers, json=BASE)
    assert response.status_code == 200
    assert preview.call_args.kwargs["recipients"] == BASE["recipients"]
    assert "actor_user_id" not in preview.call_args.kwargs
    freeze.assert_not_called()


def test_global_freeze_uses_authenticated_actor_and_no_sender():
    api, headers = client()
    payload = {**BASE, "expected_preview_fingerprint": "a" * 64,
               "expected_channel_binding_id": 12, "confirm_freeze": True}
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=47), full_access())), \
         patch.object(routes, "freeze_qa_manual_http", return_value={"campaign_id": 99}) as freeze:
        response = api.post("/api/marketing/campaigns-v2/qa-manual/freeze",
                            headers=headers, json=payload)
    assert response.status_code == 201
    assert freeze.call_args.kwargs["actor_user_id"] == 47


def test_unexpected_actor_or_provider_field_is_rejected():
    api, headers = client()
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=47), full_access())), \
         patch.object(routes, "freeze_qa_manual_http") as freeze:
        response = api.post("/api/marketing/campaigns-v2/qa-manual/freeze",
                            headers=headers, json={**BASE, "created_by_user_id": 999})
    assert response.status_code == 400
    freeze.assert_not_called()


def test_qa_freeze_fingerprint_conflict_returns_409():
    api, headers = client()
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=47), full_access())), \
         patch.object(routes, "freeze_qa_manual_http", side_effect=QAConflict("fingerprint stale")):
        response = api.post("/api/marketing/campaigns-v2/qa-manual/freeze",
                            headers=headers, json=BASE)
    assert response.status_code == 409


def test_postgres_concurrent_same_name_freeze_returns_409_before_write():
    from unittest.mock import MagicMock
    params = {**BASE, "expected_preview_fingerprint": "a" * 64,
              "expected_channel_binding_id": 12, "confirm_freeze": True, "actor_user_id": 47}
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    session.execute.return_value.scalar.return_value = False
    with patch.object(qa, "list_channel_bindings", return_value=[BINDING]), \
         patch.object(qa, "freeze_campaign_v2_qa_manual") as freeze:
        with pytest.raises(QAConflict, match="en curso"):
            qa.freeze_qa_manual_http(**params, session=session)
    session.execute.assert_called_once()
    freeze.assert_not_called()


def test_postgres_freeze_lock_success_delegates_existing_service():
    from unittest.mock import MagicMock
    params = {**BASE, "expected_preview_fingerprint": "a" * 64,
              "expected_channel_binding_id": 12, "confirm_freeze": True, "actor_user_id": 47}
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    session.execute.return_value.scalar.return_value = True
    with patch.object(qa, "list_channel_bindings", return_value=[BINDING]), \
         patch.object(qa, "freeze_campaign_v2_qa_manual", return_value={
             "campaign_id": 56, "recipient_count": 1, "source": "QA_MANUAL",
         }) as freeze:
        result = qa.freeze_qa_manual_http(**params, session=session)
    assert result["campaign_id"] == 56
    assert result["is_dispatch_authorized"] is False
    session.execute.assert_called_once()
    freeze.assert_called_once()
