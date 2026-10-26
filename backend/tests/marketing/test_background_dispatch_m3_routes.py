"""Issue #1129 M3: real Flask/JWT HTTP negative gates, always mocked services.

No DB writes and no iVentas network calls. Positive feature flags only exist in
this synthetic Flask test, never in production Config or a deployed worker.
"""
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes

BASE = "/api/marketing/campaigns-v2"
JOB_PATH = f"{BASE}/99/dispatch/jobs"
JOB_DETAIL = f"{JOB_PATH}/77"
JOB_STOP = f"{JOB_DETAIL}/stop"
MY_JOBS = f"{BASE}/dispatch/jobs/mine"

REQUEST = {
    "approval_id": 9,
    "execution_id": 41,
    "expected_manifest_digest": "a" * 64,
    "expected_pending_child_ids": [101, 102],
    "request_key": "b" * 64,
    "confirmation": "ENVIAR PENDIENTES 2",
    "confirmed": True,
    "operator_password": "synthetic-password",
}
SNAPSHOT = {
    "job_id": 77, "campaign_id": 99, "execution_id": 41,
    "status": "QUEUED", "accepted_by_provider": 0, "total_pending_at_start": 2,
    "delivery_confirmed": False, "may_auto_retry": False,
    "may_auto_resume": False,
}


@pytest.fixture
def api():
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = version("werkzeug")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="synthetic-issue1129-ci-jwt",
        CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED=False,
        CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY=False,
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=False,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=False,
    )
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def user():
    return SimpleNamespace(
        id=47, verify_password=lambda password: password == "synthetic-password",
    )


def access(**override):
    props = dict(
        is_global=True, can_manage_dispatch_config=True,
        can_send_campaigns=True, can_manage_campaigns=True,
        can_preflight_campaigns=True, branch_ids=(),
    )
    props.update(override)
    return SimpleNamespace(**props)


def enable_only_in_test(client):
    client.application.config.update(
        CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED=True,
        CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY=True,
        CAMPAIGN_V2_PROVIDER_SEND_ENABLED=True,
        CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=True,
    )


@pytest.mark.parametrize("method,path", [
    ("post", JOB_PATH), ("get", JOB_DETAIL),
    ("get", MY_JOBS), ("post", JOB_STOP),
])
def test_jwt_is_required(api, method, path):
    client, _ = api
    response = getattr(client, method)(
        path, **({"json": REQUEST} if method == "post" and path == JOB_PATH else {})
    )
    assert response.status_code == 401


@pytest.mark.parametrize("disabled", [
    "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED",
    "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY",
    "CAMPAIGN_V2_PROVIDER_SEND_ENABLED",
    "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED",
])
def test_each_flag_blocks_enqueue_before_service_or_provider(api, disabled):
    client, headers = api
    enable_only_in_test(client)
    client.application.config[disabled] = False
    with patch.object(routes, "_resolve_request_access",
                      return_value=(user(), access())), \
         patch.object(routes, "enqueue_background_job") as enqueue, \
         patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = client.post(JOB_PATH, json=REQUEST, headers=headers)
    assert response.status_code == 423
    enqueue.assert_not_called()
    provider.assert_not_called()


@pytest.mark.parametrize("override", [
    {"is_global": False},
    {"can_manage_dispatch_config": False},
    {"can_send_campaigns": False},
])
def test_scope_and_capabilities_remain_backend_enforced(api, override):
    client, headers = api
    enable_only_in_test(client)
    with patch.object(routes, "_resolve_request_access",
                      return_value=(user(), access(**override))), \
         patch.object(routes, "enqueue_background_job") as enqueue:
        response = client.post(JOB_PATH, json=REQUEST, headers=headers)
    assert response.status_code == 403
    enqueue.assert_not_called()


def test_reauthentication_required_and_untrusted_fields_rejected(api):
    client, headers = api
    enable_only_in_test(client)
    with patch.object(routes, "_resolve_request_access",
                      return_value=(user(), access())), \
         patch.object(routes, "enqueue_background_job") as enqueue:
        invalid = dict(REQUEST, operator_password="incorrect")
        assert client.post(JOB_PATH, json=invalid, headers=headers).status_code == 403
        extra = dict(REQUEST, actor_user_id=999)
        assert client.post(JOB_PATH, json=extra, headers=headers).status_code == 400
    enqueue.assert_not_called()


def test_exact_operator_scope_without_persisting_password(api):
    client, headers = api
    enable_only_in_test(client)
    with patch.object(routes, "_resolve_request_access",
                      return_value=(user(), access())), \
         patch.object(routes, "enqueue_background_job", return_value=(SNAPSHOT, True)) as enqueue, \
         patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = client.post(JOB_PATH, json=REQUEST, headers=headers)
    assert response.status_code == 202
    assert response.get_json()["job_id"] == 77
    assert enqueue.call_count == 1
    assert enqueue.call_args.kwargs["actor_user_id"] == 47
    assert enqueue.call_args.kwargs["expected_pending_child_ids"] == [101, 102]
    assert "operator_password" not in enqueue.call_args.kwargs
    provider.assert_not_called()


def test_status_stays_readable_when_worker_is_disabled(api):
    client, headers = api
    with patch.object(routes, "_resolve_request_access",
                      return_value=(user(), access())), \
         patch.object(routes, "list_background_jobs", return_value=[SNAPSHOT]) as listing, \
         patch.object(routes, "get_background_job", return_value=SNAPSHOT) as getter:
        mine = client.get(MY_JOBS, headers=headers)
        job = client.get(JOB_DETAIL, headers=headers)
    assert mine.status_code == 200
    assert mine.get_json()["background_dispatch_available"] is False
    assert len(mine.get_json()["jobs"]) == 1
    assert job.status_code == 200
    assert listing.call_args.kwargs["operator_user_id"] == 47
    assert getter.call_args.kwargs["actor_user_id"] == 47


def test_stop_is_explicit_authenticated_and_scoped(api):
    client, headers = api
    with patch.object(routes, "_resolve_request_access",
                      return_value=(user(), access())), \
         patch.object(routes, "stop_background_job", return_value={
             **SNAPSHOT, "status": "STOP_REQUESTED",
         }) as stop, \
         patch.object(routes, "IVentasBroadcastProvider") as provider:
        response = client.post(JOB_STOP, json={}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["status"] == "STOP_REQUESTED"
    assert stop.call_args.kwargs["actor_user_id"] == 47
    assert stop.call_args.kwargs["job_id"] == 77
    provider.assert_not_called()
